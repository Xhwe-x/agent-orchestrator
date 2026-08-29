#!/usr/bin/env bash
set -euo pipefail

FORCE=0
CHECK=0
UNINSTALL=0

usage() {
  echo "Usage: $0 [--check] [--force] [--uninstall]" >&2
}

for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    --check) CHECK=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

ROOT="$(cd -P "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TARGET_HOME="${AGENT_ORCHESTRATOR_HOME:-$HOME}"
TARGET_HOME_ROOT="${TARGET_HOME%/}"
[[ -n "$TARGET_HOME_ROOT" ]] || TARGET_HOME_ROOT="/"
SKILL_DEST="$TARGET_HOME_ROOT/.agents/skills/agent-orchestrator"
AGENT_DEST="$TARGET_HOME_ROOT/.codex/agents"
STATE_ROOT="$TARGET_HOME_ROOT/.agent-orchestrator"
INSTALL_MANIFEST_NAME=".agent-orchestrator-install.tsv"
INSTALL_MANIFEST="$SKILL_DEST/$INSTALL_MANIFEST_NAME"
LOCK_DIR="$STATE_ROOT/operation.lock"
LOCK_HELD=0

unsafe_destination() {
  echo "Unsafe installer destination: $1${2:+ ($2)}" >&2
  return 1
}

# Check existing destination components without resolving the configured home
# itself.  The home is the user-selected trust boundary; no descendant beneath
# it may be a symlink (including a broken symlink).
assert_safe_destination_path() {
  local path="$1" relative cursor part index
  local parts=()

  if [[ "$path" == "$TARGET_HOME_ROOT" ]]; then
    return 0
  fi
  if [[ "$TARGET_HOME_ROOT" == "/" ]]; then
    if [[ "$path" != /* ]]; then
      unsafe_destination "$path" "path escapes configured home"
      return 1
    fi
    relative="${path#/}"
  elif [[ "$path" == "$TARGET_HOME_ROOT/"* ]]; then
    relative="${path#"$TARGET_HOME_ROOT/"}"
  else
    unsafe_destination "$path" "path escapes configured home"
    return 1
  fi
  if [[ -z "$relative" ]]; then
    unsafe_destination "$path" "empty destination component"
    return 1
  fi

  IFS='/' read -r -a parts <<< "$relative"
  cursor="$TARGET_HOME_ROOT"
  for index in "${!parts[@]}"; do
    part="${parts[$index]}"
    if [[ -z "$part" || "$part" == "." || "$part" == ".." ]]; then
      unsafe_destination "$path" "unsafe destination component"
      return 1
    fi
    if [[ "$cursor" == "/" ]]; then
      cursor="/$part"
    else
      cursor="$cursor/$part"
    fi
    if [[ -L "$cursor" ]]; then
      unsafe_destination "$path" "symlink component: $cursor"
    fi
    if [[ "$index" -lt $((${#parts[@]} - 1)) && -e "$cursor" && ! -d "$cursor" ]]; then
      unsafe_destination "$path" "non-directory ancestor: $cursor"
      return 1
    fi
  done
}

# Create one directory component at a time and re-check each component after
# creation.  The configured home itself may be a user-provided symlink; only
# descendants are rejected.
ensure_safe_directory() {
  local path="$1" relative cursor part index
  local parts=()
  assert_safe_destination_path "$path" || return 1

  if [[ "$path" == "$TARGET_HOME_ROOT" ]]; then
    if [[ ! -e "$TARGET_HOME_ROOT" && ! -L "$TARGET_HOME_ROOT" ]]; then
      mkdir "$TARGET_HOME_ROOT" || { echo "Unable to create configured home: $TARGET_HOME_ROOT" >&2; return 1; }
    fi
    [[ -d "$TARGET_HOME_ROOT" ]] || { echo "Configured home is not a directory: $TARGET_HOME_ROOT" >&2; return 1; }
    return 0
  fi

  if [[ "$TARGET_HOME_ROOT" == "/" ]]; then
    relative="${path#/}"
  else
    relative="${path#"$TARGET_HOME_ROOT/"}"
  fi
  IFS='/' read -r -a parts <<< "$relative"
  cursor="$TARGET_HOME_ROOT"
  if [[ ! -e "$cursor" && ! -L "$cursor" ]]; then
    mkdir "$cursor" || { echo "Unable to create configured home: $cursor" >&2; return 1; }
  fi
  [[ -d "$cursor" ]] || { echo "Configured home is not a directory: $cursor" >&2; return 1; }

  for index in "${!parts[@]}"; do
    part="${parts[$index]}"
    if [[ "$cursor" == "/" ]]; then
      cursor="/$part"
    else
      cursor="$cursor/$part"
    fi
    if [[ -L "$cursor" ]]; then
      unsafe_destination "$path" "symlink component: $cursor"
      return 1
    fi
    if [[ -e "$cursor" ]]; then
      [[ -d "$cursor" ]] || { echo "Destination component is not a directory: $cursor" >&2; return 1; }
    else
      mkdir "$cursor" || { echo "Unable to create destination directory: $cursor" >&2; return 1; }
      [[ ! -L "$cursor" && -d "$cursor" ]] || {
        unsafe_destination "$path" "unsafe component created: $cursor"
        return 1
      }
    fi
  done
}

assert_destination_layout() {
  assert_safe_destination_path "$(dirname "$SKILL_DEST")" || return 1
  assert_safe_destination_path "$AGENT_DEST" || return 1
  assert_safe_destination_path "$STATE_ROOT" || return 1
  assert_safe_destination_path "$STATE_ROOT/operation.lock" || return 1
  assert_safe_destination_path "$STATE_ROOT/staging" || return 1
  assert_safe_destination_path "$STATE_ROOT/backups" || return 1
}

copy_file_noclobber() {
  local src="$1" dest="$2" parent temp
  parent="$(dirname "$dest")"
  ensure_safe_directory "$parent" || return 1
  assert_safe_destination_path "$dest" || return 1
  if path_exists_or_link "$dest"; then
    echo "Late or unverified destination collision detected; refusing to overwrite: $dest" >&2
    return 1
  fi
  temp="$(mktemp "$parent/.agent-orchestrator-file.XXXXXX")" || return 1
  if ! assert_safe_destination_path "$temp" || ! cp "$src" "$temp"; then
    rm -f -- "$temp"
    return 1
  fi
  if ! assert_safe_destination_path "$dest" || path_exists_or_link "$dest" || ! ln "$temp" "$dest" 2>/dev/null; then
    rm -f -- "$temp"
    echo "Late or unverified destination collision detected; refusing to overwrite: $dest" >&2
    return 1
  fi
  rm -f -- "$temp"
}

VERSION="$(awk -F '"' '/^version = "/ {print $2; exit}' "$ROOT/manifest.toml")"
if [[ -z "$VERSION" ]]; then
  echo "Unable to read version from manifest.toml" >&2
  exit 1
fi

sha256_file() {
  local path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$path" | awk '{print $1}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$path" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$path" | awk '{print $NF}'
  else
    echo "No SHA-256 utility found (sha256sum, shasum, or openssl required)." >&2
    return 1
  fi
}

SKILL_RUNTIME_FILES=(
  "SKILL.md"
  "agents/openai.yaml"
  "references/orchestration.md"
  "references/agent-contract.md"
  "references/models.md"
  "references/codex.md"
)
AGENT_PROFILE_FILES=(
  "backend-worker.toml"
  "docs-worker.toml"
  "explorer-worker.toml"
  "frontend-worker.toml"
  "generic-worker.toml"
  "review-worker.toml"
  "test-worker.toml"
)

source_path_is_safe() {
  local relative="$1" cursor="$ROOT" part
  local parts=()
  IFS='/' read -r -a parts <<< "$relative"
  for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != "." && "$part" != ".." ]] || return 1
    cursor="$cursor/$part"
    [[ ! -L "$cursor" ]] || return 1
  done
  [[ -f "$cursor" ]]
}

validate_source() {
  local relative name
  for relative in "manifest.toml" "${SKILL_RUNTIME_FILES[@]}"; do
    source_path_is_safe "$relative" || { echo "Missing or unsafe installer source: $ROOT/$relative" >&2; return 1; }
  done
  for name in "${AGENT_PROFILE_FILES[@]}"; do
    relative="templates/codex-agents/$name"
    source_path_is_safe "$relative" || { echo "Missing or unsafe canonical Agent source: $ROOT/$relative" >&2; return 1; }
  done
}

if [[ "$UNINSTALL" -ne 1 ]]; then
  validate_source
fi

AGENT_SOURCES=()
for name in "${AGENT_PROFILE_FILES[@]}"; do
  AGENT_SOURCES+=("$ROOT/templates/codex-agents/$name")
done

is_safe_relative_path() {
  local value="$1" part
  [[ -n "$value" && "$value" != /* && "$value" != *\\* && "$value" != *:* ]] || return 1
  local parts=()
  IFS='/' read -r -a parts <<< "$value"
  [[ ${#parts[@]} -gt 0 ]] || return 1
  for part in "${parts[@]}"; do
    [[ -n "$part" && "$part" != "." && "$part" != ".." ]] || return 1
  done
}

path_exists_or_link() {
  [[ -e "$1" || -L "$1" ]]
}

is_expected_skill_path() {
  local candidate="$1" expected
  for expected in "${SKILL_RUNTIME_FILES[@]}"; do
    [[ "$candidate" == "$expected" ]] && return 0
  done
  return 1
}

is_expected_agent_name() {
  local candidate="$1" src
  [[ "$candidate" != */* && "$candidate" != *\\* && -n "$candidate" ]] || return 1
  for src in "${AGENT_SOURCES[@]}"; do
    [[ "$(basename "$src")" == "$candidate" ]] && return 0
  done
  return 1
}

array_contains() {
  local needle="$1"; shift
  local value
  for value in "$@"; do
    [[ "$value" == "$needle" ]] && return 0
  done
  return 1
}

LEGACY_ORCHESTRATOR_PATH="$AGENT_DEST/orchestrator.toml"
LEGACY_ORCHESTRATOR_HASHES=()
LEGACY_ORCHESTRATOR_STATUS="none"

load_legacy_orchestrator_hashes() {
  local in_section=0 line hash
  while IFS= read -r line; do
    if [[ "$line" == "[compatibility]" ]]; then
      in_section=1
      continue
    fi
    if [[ "$in_section" -eq 1 && "$line" == \[* ]]; then
      break
    fi
    if [[ "$in_section" -eq 1 ]]; then
      hash="$(printf '%s\n' "$line" | sed -n 's/^[[:space:]]*"\([0-9A-Fa-f]\{64\}\)"[[:space:]]*,\{0,1\}[[:space:]]*$/\1/p')"
      if [[ -n "$hash" ]]; then
        LEGACY_ORCHESTRATOR_HASHES+=("$(printf '%s' "$hash" | tr '[:upper:]' '[:lower:]')")
      fi
    fi
  done < "$ROOT/manifest.toml"
  [[ ${#LEGACY_ORCHESTRATOR_HASHES[@]} -gt 0 ]] || { echo "manifest.toml contains no legacy orchestrator compatibility fingerprints." >&2; return 1; }
}

inspect_legacy_orchestrator() {
  assert_safe_destination_path "$AGENT_DEST" || return 1
  LEGACY_ORCHESTRATOR_STATUS="none"
  if [[ ! -e "$LEGACY_ORCHESTRATOR_PATH" && ! -L "$LEGACY_ORCHESTRATOR_PATH" ]]; then
    return 0
  fi
  if [[ -L "$LEGACY_ORCHESTRATOR_PATH" || ! -f "$LEGACY_ORCHESTRATOR_PATH" ]]; then
    LEGACY_ORCHESTRATOR_STATUS="unknown"
    return 0
  fi
  local current
  current="$(sha256_file "$LEGACY_ORCHESTRATOR_PATH")"
  current="$(printf '%s' "$current" | tr '[:upper:]' '[:lower:]')"
  if array_contains "$current" "${LEGACY_ORCHESTRATOR_HASHES[@]}"; then
    LEGACY_ORCHESTRATOR_STATUS="known"
  else
    LEGACY_ORCHESTRATOR_STATUS="unknown"
  fi
}

load_legacy_orchestrator_hashes
assert_destination_layout

acquire_operation_lock() {
  ensure_safe_directory "$STATE_ROOT" || return 1
  if mkdir "$LOCK_DIR" 2>/dev/null; then
    assert_safe_destination_path "$LOCK_DIR" || {
      rm -rf -- "$LOCK_DIR"
      return 1
    }
    local pid_temp
    if ! pid_temp="$(mktemp "$LOCK_DIR/.pid.XXXXXX" 2>/dev/null)"; then
      rm -rf -- "$LOCK_DIR"
      echo "Unable to initialize the operation lock." >&2
      return 1
    fi
    if ! assert_safe_destination_path "$pid_temp" || ! printf '%s\n' "$$" > "$pid_temp" ||
       ! assert_safe_destination_path "$LOCK_DIR/pid" || ! ln "$pid_temp" "$LOCK_DIR/pid" 2>/dev/null; then
      rm -f -- "$pid_temp"
      rm -rf -- "$LOCK_DIR"
      echo "Unable to initialize the operation lock." >&2
      return 1
    fi
    rm -f -- "$pid_temp"
    LOCK_HELD=1
    return 0
  fi

  local owner_pid="" stale_dir
  assert_safe_destination_path "$LOCK_DIR" || return 1
  assert_safe_destination_path "$LOCK_DIR/pid" || return 1
  if [[ ! -f "$LOCK_DIR/pid" || ! -r "$LOCK_DIR/pid" ]]; then
    echo "Another Agent Orchestrator operation is already running or acquiring the operation lock." >&2
    return 1
  fi
  if ! owner_pid="$(<"$LOCK_DIR/pid")" || [[ ! "$owner_pid" =~ ^[1-9][0-9]*$ ]]; then
    echo "Another Agent Orchestrator operation is already running or acquiring the operation lock." >&2
    return 1
  fi
  local kill_status
  if kill -0 "$owner_pid" 2>/dev/null; then
    kill_status=0
  else
    kill_status=$?
  fi
  case "$kill_status" in
    0)
      echo "Another Agent Orchestrator operation is already running (pid $owner_pid)." >&2
      return 1
      ;;
    1)
      ;;
    *)
      echo "Another Agent Orchestrator operation is already running or acquiring the operation lock." >&2
      return 1
      ;;
  esac

  stale_dir="$STATE_ROOT/operation.lock.stale.$$.$RANDOM"
  assert_safe_destination_path "$stale_dir" || return 1
  if path_exists_or_link "$stale_dir"; then
    echo "Another Agent Orchestrator operation is already running or acquiring the operation lock." >&2
    return 1
  fi
  if ! mv "$LOCK_DIR" "$stale_dir" 2>/dev/null; then
    echo "Another Agent Orchestrator operation is already running or acquiring the operation lock." >&2
    return 1
  fi
  assert_safe_destination_path "$stale_dir" || return 1
  rm -rf -- "$stale_dir"
  assert_safe_destination_path "$LOCK_DIR" || return 1
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "Another Agent Orchestrator operation acquired the lock first." >&2
    return 1
  fi
  assert_safe_destination_path "$LOCK_DIR" || return 1
  if ! pid_temp="$(mktemp "$LOCK_DIR/.pid.XXXXXX" 2>/dev/null)" ||
     ! assert_safe_destination_path "$pid_temp" || ! printf '%s\n' "$$" > "$pid_temp" ||
     ! assert_safe_destination_path "$LOCK_DIR/pid" || ! ln "$pid_temp" "$LOCK_DIR/pid" 2>/dev/null; then
    [[ -n "${pid_temp:-}" ]] && rm -f -- "$pid_temp"
    rm -rf -- "$LOCK_DIR"
    echo "Unable to initialize the operation lock." >&2
    return 1
  fi
  rm -f -- "$pid_temp"
  LOCK_HELD=1
}

release_operation_lock() {
  if [[ "$LOCK_HELD" -eq 1 ]]; then
    if assert_safe_destination_path "$LOCK_DIR"; then
      rm -rf -- "$LOCK_DIR"
    else
      echo "Unsafe operation lock path; leaving lock in place." >&2
    fi
    LOCK_HELD=0
  fi
}

collect_collisions() {
  assert_safe_destination_path "$(dirname "$SKILL_DEST")" || return 1
  assert_safe_destination_path "$AGENT_DEST" || return 1
  COLLISIONS=()
  path_exists_or_link "$SKILL_DEST" && COLLISIONS+=("$SKILL_DEST")
  local src dest
  for src in "${AGENT_SOURCES[@]}"; do
    dest="$AGENT_DEST/$(basename "$src")"
    if path_exists_or_link "$dest"; then COLLISIONS+=("$dest"); fi
  done
  return 0
}

installed_skill_file_is_regular_no_symlink_components() {
  local relative="$1" cursor="$SKILL_DEST" part
  [[ -d "$SKILL_DEST" && ! -L "$SKILL_DEST" ]] || return 1
  local parts=()
  IFS='/' read -r -a parts <<< "$relative"
  for part in "${parts[@]}"; do
    cursor="$cursor/$part"
    [[ ! -L "$cursor" ]] || return 1
  done
  [[ -f "$cursor" ]]
}

build_expected_installed_skill_entries() {
  EXPECTED_INSTALLED_SKILL_ENTRIES=("$INSTALL_MANIFEST_NAME")
  local relative parent
  for relative in "${SKILL_RUNTIME_FILES[@]}"; do
    if ! array_contains "$relative" "${EXPECTED_INSTALLED_SKILL_ENTRIES[@]}"; then
      EXPECTED_INSTALLED_SKILL_ENTRIES+=("$relative")
    fi
    parent="${relative%/*}"
    while [[ "$parent" != "$relative" && -n "$parent" && "$parent" != "." ]]; do
      if ! array_contains "$parent" "${EXPECTED_INSTALLED_SKILL_ENTRIES[@]}"; then
        EXPECTED_INSTALLED_SKILL_ENTRIES+=("$parent")
      fi
      relative="$parent"
      parent="${relative%/*}"
    done
  done
}

read_install_manifest() {
  MANAGED_SKILL_PATHS=()
  MANAGED_SKILL_HASHES=()
  MANAGED_AGENT_NAMES=()
  MANAGED_AGENT_HASHES=()
  MANAGED_LEGACY_ORCHESTRATOR=0
  [[ -d "$SKILL_DEST" && ! -L "$SKILL_DEST" ]] || { echo "Managed Skill destination is missing, non-directory, or a symlink: $SKILL_DEST" >&2; return 1; }
  [[ -f "$INSTALL_MANIFEST" && ! -L "$INSTALL_MANIFEST" ]] || { echo "Managed install manifest not found or is not a regular owned file: $INSTALL_MANIFEST" >&2; return 1; }

  local kind path hash normalized_hash version_entries=0 src expected expected_agent_entries
  while IFS=$'\t' read -r kind path hash; do
    case "$kind" in
      version)
        [[ "$path" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$hash" == "-" ]] || { echo "Install manifest version entry is invalid." >&2; return 1; }
        version_entries=$((version_entries + 1))
        ;;
      skill)
        is_safe_relative_path "$path" || { echo "Unsafe managed Skill path in install manifest: $path" >&2; return 1; }
        is_expected_skill_path "$path" || { echo "Unsafe or unknown managed Skill path in install manifest: $path" >&2; return 1; }
        [[ "$hash" =~ ^[0-9A-Fa-f]{64}$ ]] || { echo "Invalid managed Skill hash in install manifest: $path" >&2; return 1; }
        if array_contains "$path" "${MANAGED_SKILL_PATHS[@]}"; then
          echo "Duplicate managed Skill path in install manifest: $path" >&2; return 1
        fi
        MANAGED_SKILL_PATHS+=("$path")
        MANAGED_SKILL_HASHES+=("$(printf '%s' "$hash" | tr '[:upper:]' '[:lower:]')")
        ;;
      agent)
        [[ "$hash" =~ ^[0-9A-Fa-f]{64}$ ]] || { echo "Invalid managed Agent hash in install manifest: $path" >&2; return 1; }
        normalized_hash="$(printf '%s' "$hash" | tr '[:upper:]' '[:lower:]')"
        if [[ "$path" == "orchestrator.toml" ]]; then
          array_contains "$normalized_hash" "${LEGACY_ORCHESTRATOR_HASHES[@]}" || { echo "Install manifest contains an unrecognized legacy orchestrator fingerprint." >&2; return 1; }
          MANAGED_LEGACY_ORCHESTRATOR=1
        else
          is_expected_agent_name "$path" || { echo "Unsafe or unknown managed Agent name in install manifest: $path" >&2; return 1; }
        fi
        if array_contains "$path" "${MANAGED_AGENT_NAMES[@]}"; then
          echo "Duplicate managed Agent name in install manifest: $path" >&2; return 1
        fi
        MANAGED_AGENT_NAMES+=("$path")
        MANAGED_AGENT_HASHES+=("$normalized_hash")
        ;;
      "") ;;
      *) echo "Invalid managed install manifest entry: $kind" >&2; return 1 ;;
    esac
  done < "$INSTALL_MANIFEST"

  [[ "$version_entries" -eq 1 ]] || { echo "Install manifest must contain exactly one version entry." >&2; return 1; }
  [[ ${#MANAGED_SKILL_PATHS[@]} -eq ${#SKILL_RUNTIME_FILES[@]} ]] || { echo "Install manifest must contain exactly ${#SKILL_RUNTIME_FILES[@]} canonical runtime Skill files." >&2; return 1; }
  for expected in "${SKILL_RUNTIME_FILES[@]}"; do
    array_contains "$expected" "${MANAGED_SKILL_PATHS[@]}" || { echo "Install manifest missing managed Skill file: $expected" >&2; return 1; }
  done
  expected_agent_entries=$((${#AGENT_SOURCES[@]} + MANAGED_LEGACY_ORCHESTRATOR))
  [[ ${#MANAGED_AGENT_NAMES[@]} -eq "$expected_agent_entries" ]] || { echo "Install manifest must contain ${#AGENT_SOURCES[@]} canonical worker Agent files, plus at most one recognized legacy orchestrator.toml." >&2; return 1; }
  for src in "${AGENT_SOURCES[@]}"; do
    expected="$(basename "$src")"
    array_contains "$expected" "${MANAGED_AGENT_NAMES[@]}" || { echo "Install manifest missing managed Agent: $expected" >&2; return 1; }
  done
}

classify_collisions() {
  MANAGED_COLLISIONS=()
  UNMANAGED_COLLISIONS=()
  EXISTING_INSTALL_MANAGED=0

  if path_exists_or_link "$SKILL_DEST" && [[ -d "$SKILL_DEST" && ! -L "$SKILL_DEST" && -f "$INSTALL_MANIFEST" && ! -L "$INSTALL_MANIFEST" ]]; then
    if read_install_manifest >/dev/null 2>&1; then
      EXISTING_INSTALL_MANAGED=1
    fi
  fi

  local collision name
  for collision in "${COLLISIONS[@]}"; do
    if [[ "$EXISTING_INSTALL_MANAGED" -eq 1 ]]; then
      if [[ "$collision" == "$SKILL_DEST" ]]; then
        MANAGED_COLLISIONS+=("$collision")
        continue
      fi
      name="$(basename "$collision")"
      if array_contains "$name" "${MANAGED_AGENT_NAMES[@]}"; then
        MANAGED_COLLISIONS+=("$collision")
        continue
      fi
    fi
    UNMANAGED_COLLISIONS+=("$collision")
  done
}

check_managed_integrity() {
  MODIFIED_MANAGED=()
  LEGACY_MANAGED_OWNERSHIP_UNKNOWN=0
  local i current expected path name relative actual
  for i in "${!MANAGED_SKILL_PATHS[@]}"; do
    relative="${MANAGED_SKILL_PATHS[$i]}"
    path="$SKILL_DEST/$relative"
    expected="${MANAGED_SKILL_HASHES[$i]}"
    if ! installed_skill_file_is_regular_no_symlink_components "$relative"; then
      MODIFIED_MANAGED+=("$path (missing, non-regular, or symlinked component)")
      continue
    fi
    current="$(sha256_file "$path")"
    [[ "$current" == "$expected" ]] || MODIFIED_MANAGED+=("$path")
  done

  build_expected_installed_skill_entries
  while IFS= read -r -d '' actual; do
    relative="${actual#"$SKILL_DEST"/}"
    if ! array_contains "$relative" "${EXPECTED_INSTALLED_SKILL_ENTRIES[@]}"; then
      MODIFIED_MANAGED+=("$actual (unmanaged extra content)")
    fi
  done < <(find "$SKILL_DEST" -mindepth 1 -print0)
  for i in "${!MANAGED_AGENT_NAMES[@]}"; do
    name="${MANAGED_AGENT_NAMES[$i]}"
    path="$AGENT_DEST/$name"
    expected="${MANAGED_AGENT_HASHES[$i]}"
    if [[ ! -f "$path" || -L "$path" ]]; then
      MODIFIED_MANAGED+=("$path (missing or non-regular)")
      if [[ "$name" == "orchestrator.toml" && ( -e "$path" || -L "$path" ) ]]; then
        LEGACY_MANAGED_OWNERSHIP_UNKNOWN=1
      fi
      continue
    fi
    current="$(sha256_file "$path")"
    current="$(printf '%s' "$current" | tr '[:upper:]' '[:lower:]')"
    if [[ "$name" == "orchestrator.toml" ]] && ! array_contains "$current" "${LEGACY_ORCHESTRATOR_HASHES[@]}"; then
      LEGACY_MANAGED_OWNERSHIP_UNKNOWN=1
    fi
    if [[ "$current" != "$expected" ]]; then MODIFIED_MANAGED+=("$path"); fi
  done
  return 0
}

if [[ "$CHECK" -ne 1 ]]; then
  acquire_operation_lock
  trap release_operation_lock EXIT
fi

if [[ "$UNINSTALL" -eq 1 ]]; then
  if [[ ! -d "$SKILL_DEST" || -L "$SKILL_DEST" || ! -f "$INSTALL_MANIFEST" || -L "$INSTALL_MANIFEST" ]]; then
    collect_collisions
    inspect_legacy_orchestrator
    UNMANAGED_UNINSTALL_TARGETS=("${COLLISIONS[@]}")
    if [[ "$LEGACY_ORCHESTRATOR_STATUS" != "none" ]]; then
      UNMANAGED_UNINSTALL_TARGETS+=("$LEGACY_ORCHESTRATOR_PATH")
    fi
    if [[ "$CHECK" -eq 1 ]]; then
      if [[ ${#UNMANAGED_UNINSTALL_TARGETS[@]} -eq 0 ]]; then
        echo "CHECK PASS: no managed installation found; uninstall would make no changes."
      else
        echo "CHECK PASS: no managed installation found; ${#UNMANAGED_UNINSTALL_TARGETS[@]} unmanaged/unverified target(s) are present. A real uninstall is blocked and --force will not claim them."
        printf '  %s\n' "${UNMANAGED_UNINSTALL_TARGETS[@]}"
      fi
      exit 0
    fi
    if [[ ${#UNMANAGED_UNINSTALL_TARGETS[@]} -eq 0 ]]; then
      echo "No managed installation found; nothing to uninstall."
      exit 0
    fi
    echo "Refusing to uninstall because no valid managed install manifest exists for the active target(s):" >&2
    printf '  %s\n' "${UNMANAGED_UNINSTALL_TARGETS[@]}" >&2
    echo "These targets are unmanaged or unverified; --force will not claim them." >&2
    exit 1
  fi

  read_install_manifest
  check_managed_integrity
  if [[ "$CHECK" -eq 1 ]]; then
    if [[ "$LEGACY_MANAGED_OWNERSHIP_UNKNOWN" -eq 1 ]]; then
      echo "CHECK PASS: uninstall preflight completed without mutation; active orchestrator.toml no longer matches a recognized legacy fingerprint, so a real uninstall is blocked even with --force. Move or remove that user-owned profile explicitly first."
      exit 0
    fi
    if [[ ${#MODIFIED_MANAGED[@]} -gt 0 ]]; then
      if [[ "$FORCE" -eq 1 ]]; then
        echo "CHECK PASS: uninstall preflight completed without mutation; --force would back up and remove ${#MODIFIED_MANAGED[@]} modified managed file(s)."
      else
        echo "CHECK PASS: uninstall preflight completed without mutation; ${#MODIFIED_MANAGED[@]} modified managed file(s) found. A real uninstall requires --force."
      fi
      printf '  %s\n' "${MODIFIED_MANAGED[@]}"
    else
      echo "CHECK PASS: uninstall preflight completed without mutation; managed installation can be removed without --force."
    fi
    exit 0
  fi

  if [[ "$LEGACY_MANAGED_OWNERSHIP_UNKNOWN" -eq 1 ]]; then
    echo "Refusing to uninstall because active orchestrator.toml no longer matches a recognized Agent Orchestrator legacy fingerprint." >&2
    echo "This profile may now be user-owned. Move or remove it explicitly before uninstalling; --force will not claim it." >&2
    exit 1
  fi

  if [[ ${#MODIFIED_MANAGED[@]} -gt 0 && "$FORCE" -ne 1 ]]; then
    echo "Refusing to uninstall because managed files changed after installation:" >&2
    printf '  %s\n' "${MODIFIED_MANAGED[@]}" >&2
    echo "Re-run with --force to remove the managed installation after backup." >&2
    exit 1
  fi

  timestamp="$(date +%Y%m%d%H%M%S)"
  BACKUP_ROOT="$STATE_ROOT/backups/uninstall-$timestamp-$$"
  ensure_safe_directory "$BACKUP_ROOT/agents"
  assert_safe_destination_path "$SKILL_DEST"
  assert_safe_destination_path "$BACKUP_ROOT/skill"
  rollback_uninstall() {
    local status=$?
    trap - ERR INT TERM
    if [[ -e "$BACKUP_ROOT/skill" && ! -e "$SKILL_DEST" ]]; then
      if ensure_safe_directory "$(dirname "$SKILL_DEST")" &&
         assert_safe_destination_path "$BACKUP_ROOT/skill" &&
         assert_safe_destination_path "$SKILL_DEST"; then
        mv "$BACKUP_ROOT/skill" "$SKILL_DEST"
      fi
    fi
    ensure_safe_directory "$AGENT_DEST" || true
    local src
    for src in "$BACKUP_ROOT"/agents/*.toml; do
      [[ -e "$src" ]] || continue
      if assert_safe_destination_path "$src" &&
         assert_safe_destination_path "$AGENT_DEST/$(basename "$src")"; then
        mv "$src" "$AGENT_DEST/$(basename "$src")"
      fi
    done
    echo "Uninstall failed; managed targets were rolled back." >&2
    exit "$status"
  }
  trap rollback_uninstall ERR INT TERM
  assert_safe_destination_path "$SKILL_DEST"
  assert_safe_destination_path "$BACKUP_ROOT/skill"
  mv "$SKILL_DEST" "$BACKUP_ROOT/skill"
  for name in "${MANAGED_AGENT_NAMES[@]}"; do
    if path_exists_or_link "$AGENT_DEST/$name"; then
      assert_safe_destination_path "$AGENT_DEST/$name"
      assert_safe_destination_path "$BACKUP_ROOT/agents/$name"
      mv "$AGENT_DEST/$name" "$BACKUP_ROOT/agents/$name"
    fi
  done
  trap - ERR INT TERM
  echo "Uninstalled Agent Orchestrator from active Codex paths."
  echo "Backup: $BACKUP_ROOT"
  exit 0
fi

collect_collisions
classify_collisions
inspect_legacy_orchestrator
if [[ "$CHECK" -eq 1 ]]; then
  if [[ ${#UNMANAGED_COLLISIONS[@]} -gt 0 ]]; then
    echo "CHECK PASS: source-valid, non-mutating preflight; ${#UNMANAGED_COLLISIONS[@]} unmanaged target collision(s) found. A real installation is blocked; --force will not replace user-owned or unverified targets."
    printf '  %s\n' "${UNMANAGED_COLLISIONS[@]}"
  elif [[ ${#MANAGED_COLLISIONS[@]} -gt 0 ]]; then
    if [[ "$FORCE" -eq 1 ]]; then
      echo "CHECK PASS: source-valid, non-mutating preflight; --force would replace ${#MANAGED_COLLISIONS[@]} verified managed collision(s)."
    else
      echo "CHECK PASS: source-valid, non-mutating preflight; ${#MANAGED_COLLISIONS[@]} verified managed collision(s) found. A real installation requires --force."
    fi
  else
    echo "CHECK PASS: source-valid, non-mutating preflight; no target collisions found."
  fi
  if [[ "$LEGACY_ORCHESTRATOR_STATUS" == "known" ]]; then
    echo "CHECK INFO: a known legacy orchestrator.toml would be backed up and deactivated during a real installation."
  elif [[ "$LEGACY_ORCHESTRATOR_STATUS" == "unknown" ]]; then
    echo "CHECK INFO: unmanaged orchestrator.toml is present, so a real installation is blocked until it is moved or removed manually; --force will not replace it."
  fi
  exit 0
fi

if [[ "$LEGACY_ORCHESTRATOR_STATUS" == "unknown" ]]; then
  echo "Refusing installation because unmanaged orchestrator.toml is present: $LEGACY_ORCHESTRATOR_PATH" >&2
  echo "No files were changed. Move or remove that user-owned profile explicitly; --force will not replace it." >&2
  exit 1
fi

if [[ ${#UNMANAGED_COLLISIONS[@]} -gt 0 ]]; then
  echo "Refusing installation because unmanaged or unverified target collisions exist:" >&2
  printf '  %s\n' "${UNMANAGED_COLLISIONS[@]}" >&2
  echo "No files were changed. --force only replaces targets proven to belong to an existing managed Agent Orchestrator installation." >&2
  exit 1
fi

if [[ ${#MANAGED_COLLISIONS[@]} -gt 0 && "$FORCE" -ne 1 ]]; then
  echo "Refusing installation because verified managed target collisions exist:" >&2
  printf '  %s\n' "${MANAGED_COLLISIONS[@]}" >&2
  echo "No files were changed. Re-run with --force only if replacement is intentional." >&2
  exit 1
fi

ensure_safe_directory "$STATE_ROOT/staging"
STAGE="$(mktemp -d "$STATE_ROOT/staging/install.XXXXXX")"
assert_safe_destination_path "$STAGE"
cleanup_stage() {
  if assert_safe_destination_path "$STAGE"; then
    rm -rf -- "$STAGE"
  fi
  release_operation_lock
}
trap cleanup_stage EXIT

ensure_safe_directory "$STAGE/skill"
ensure_safe_directory "$STAGE/agents"
for relative in "${SKILL_RUNTIME_FILES[@]}"; do
  parent="$(dirname "$relative")"
  if [[ "$parent" == "." ]]; then
    parent="$STAGE/skill"
  else
    parent="$STAGE/skill/$parent"
  fi
  ensure_safe_directory "$parent"
  copy_file_noclobber "$ROOT/$relative" "$STAGE/skill/$relative"
done
for src in "${AGENT_SOURCES[@]}"; do
  copy_file_noclobber "$src" "$STAGE/agents/$(basename "$src")"
done

STAGED_MANIFEST="$STAGE/skill/$INSTALL_MANIFEST_NAME"
assert_safe_destination_path "$STAGED_MANIFEST"
if path_exists_or_link "$STAGED_MANIFEST"; then
  echo "Unexpected staged manifest collision: $STAGED_MANIFEST" >&2
  exit 1
fi
STAGED_MANIFEST_TEMP="$(mktemp "$STAGE/skill/.agent-orchestrator-manifest.XXXXXX")"
assert_safe_destination_path "$STAGED_MANIFEST_TEMP"
{
  printf 'version\t%s\t-\n' "$VERSION"
  while IFS= read -r path; do
    relative="${path#"$STAGE/skill/"}"
    printf 'skill\t%s\t%s\n' "$relative" "$(sha256_file "$path")"
  done < <(find "$STAGE/skill" -type f ! -name "$INSTALL_MANIFEST_NAME" | LC_ALL=C sort)
  for src in "$STAGE"/agents/*.toml; do
    printf 'agent\t%s\t%s\n' "$(basename "$src")" "$(sha256_file "$src")"
  done
} > "$STAGED_MANIFEST_TEMP"
assert_safe_destination_path "$STAGED_MANIFEST"
if ! ln "$STAGED_MANIFEST_TEMP" "$STAGED_MANIFEST" 2>/dev/null; then
  rm -f -- "$STAGED_MANIFEST_TEMP"
  echo "Unexpected staged manifest collision: $STAGED_MANIFEST" >&2
  exit 1
fi
rm -f -- "$STAGED_MANIFEST_TEMP"

# Re-check just before committing in case a managed target appeared during staging.
assert_destination_layout
collect_collisions
classify_collisions
inspect_legacy_orchestrator
if [[ "$LEGACY_ORCHESTRATOR_STATUS" == "unknown" ]]; then
  echo "Unmanaged orchestrator.toml appeared or changed during staging; no managed target was changed." >&2
  exit 1
fi
if [[ ${#UNMANAGED_COLLISIONS[@]} -gt 0 ]]; then
  echo "Unmanaged or unverified target collision appeared during staging; no managed target was changed." >&2
  printf '  %s\n' "${UNMANAGED_COLLISIONS[@]}" >&2
  exit 1
fi
if [[ ${#MANAGED_COLLISIONS[@]} -gt 0 && "$FORCE" -ne 1 ]]; then
  echo "Verified managed target collision appeared during staging; no managed target was changed." >&2
  printf '  %s\n' "${MANAGED_COLLISIONS[@]}" >&2
  exit 1
fi

BACKUP_ROOT=""
if [[ ${#MANAGED_COLLISIONS[@]} -gt 0 || "$LEGACY_ORCHESTRATOR_STATUS" == "known" ]]; then
  timestamp="$(date +%Y%m%d%H%M%S)"
  BACKUP_ROOT="$STATE_ROOT/backups/install-$timestamp-$$"
  ensure_safe_directory "$BACKUP_ROOT/agents"
fi

ROLLED_BACK=0
SKILL_BACKED_UP=0
NEW_SKILL_INSTALLED=0
BACKED_UP_AGENT_NAMES=()
NEW_AGENT_NAMES=()
LEGACY_ORCHESTRATOR_BACKED_UP=0

install_agent_noclobber() {
  local src="$1" dest="$2" temp
  temp="$(mktemp "$AGENT_DEST/.agent-orchestrator-agent.XXXXXX")" || return 1
  if ! cp "$src" "$temp" || ! chmod 0644 "$temp"; then
    rm -f "$temp"
    return 1
  fi
  if ! ln "$temp" "$dest" 2>/dev/null; then
    rm -f "$temp"
    echo "Late or unverified Agent collision detected during commit; refusing to overwrite: $dest" >&2
    return 1
  fi
  rm -f "$temp"
}

install_skill_noclobber() {
  local relative dest
  if ! mkdir "$SKILL_DEST" 2>/dev/null; then
    echo "Late or unverified Skill collision detected during commit; refusing to overwrite: $SKILL_DEST" >&2
    return 1
  fi
  NEW_SKILL_INSTALLED=1
  for relative in "${SKILL_RUNTIME_FILES[@]}" "$INSTALL_MANIFEST_NAME"; do
    dest="$SKILL_DEST/$relative"
    mkdir -p "$(dirname "$dest")"
    cp "$STAGE/skill/$relative" "$dest"
  done
}

rollback_install() {
  local status=$?
  [[ "$ROLLED_BACK" -eq 1 ]] && exit "$status"
  ROLLED_BACK=1
  trap - ERR INT TERM
  local name
  if [[ "$NEW_SKILL_INSTALLED" -eq 1 && -e "$SKILL_DEST" ]]; then
    rm -rf "$SKILL_DEST"
  fi
  for name in "${NEW_AGENT_NAMES[@]}"; do
    rm -f "$AGENT_DEST/$name"
  done
  if [[ "$SKILL_BACKED_UP" -eq 1 && -e "$BACKUP_ROOT/skill" ]]; then
    mkdir -p "$(dirname "$SKILL_DEST")"
    mv "$BACKUP_ROOT/skill" "$SKILL_DEST"
  fi
  if [[ -n "$BACKUP_ROOT" ]]; then
    mkdir -p "$AGENT_DEST"
    for name in "${BACKED_UP_AGENT_NAMES[@]}"; do
      if [[ -e "$BACKUP_ROOT/agents/$name" ]]; then
        mv "$BACKUP_ROOT/agents/$name" "$AGENT_DEST/$name"
      fi
    done
    if [[ "$LEGACY_ORCHESTRATOR_BACKED_UP" -eq 1 && -e "$BACKUP_ROOT/agents/orchestrator.toml" ]]; then
      mv "$BACKUP_ROOT/agents/orchestrator.toml" "$LEGACY_ORCHESTRATOR_PATH"
    fi
  fi
  echo "Installation failed; only changes completed by this install attempt were rolled back." >&2
  exit "$status"
}
trap rollback_install ERR INT TERM

mkdir -p "$(dirname "$SKILL_DEST")" "$AGENT_DEST"
if path_exists_or_link "$SKILL_DEST"; then
  if ! array_contains "$SKILL_DEST" "${MANAGED_COLLISIONS[@]}"; then
    echo "Late unverified Skill collision appeared during commit; refusing to take ownership: $SKILL_DEST" >&2
    false
  fi
  mv "$SKILL_DEST" "$BACKUP_ROOT/skill"
  SKILL_BACKED_UP=1
fi
for src in "${AGENT_SOURCES[@]}"; do
  name="$(basename "$src")"
  dest="$AGENT_DEST/$name"
  if path_exists_or_link "$dest"; then
    if ! array_contains "$dest" "${MANAGED_COLLISIONS[@]}"; then
      echo "Late unverified Agent collision appeared during commit; refusing to take ownership: $dest" >&2
      false
    fi
    mv "$dest" "$BACKUP_ROOT/agents/$name"
    BACKED_UP_AGENT_NAMES+=("$name")
  fi
done
inspect_legacy_orchestrator
if [[ "$LEGACY_ORCHESTRATOR_STATUS" == "unknown" ]]; then
  echo "Legacy orchestrator ownership changed during commit; refusing to take ownership: $LEGACY_ORCHESTRATOR_PATH" >&2
  false
elif [[ "$LEGACY_ORCHESTRATOR_STATUS" == "known" ]]; then
  [[ -n "$BACKUP_ROOT" ]] || { echo "Known legacy orchestrator appeared too late for a safe migration; retry the install." >&2; false; }
  mv "$LEGACY_ORCHESTRATOR_PATH" "$BACKUP_ROOT/agents/orchestrator.toml"
  LEGACY_ORCHESTRATOR_BACKED_UP=1
fi

install_skill_noclobber
for src in "$STAGE"/agents/*.toml; do
  name="$(basename "$src")"
  dest="$AGENT_DEST/$name"
  install_agent_noclobber "$src" "$dest"
  NEW_AGENT_NAMES+=("$name")
done

# Post-install integrity verification against the newly written managed manifest.
read_install_manifest
check_managed_integrity
if [[ ${#MODIFIED_MANAGED[@]} -gt 0 ]]; then
  echo "Post-install integrity verification failed:" >&2
  printf '  %s\n' "${MODIFIED_MANAGED[@]}" >&2
  false
fi
trap - ERR INT TERM

printf 'Installed Agent Orchestrator v%s\n' "$VERSION"
echo "Runtime skill: $SKILL_DEST"
echo "Agent profiles: $AGENT_DEST"
if [[ -n "$BACKUP_ROOT" ]]; then
  echo "Backup: $BACKUP_ROOT"
fi
