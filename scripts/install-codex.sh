#!/usr/bin/env bash
set -euo pipefail

FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--force]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_HOME="${AGENT_ORCHESTRATOR_HOME:-$HOME}"
SKILL_DEST="$TARGET_HOME/.agents/skills/agent-orchestrator"
AGENT_DEST="$TARGET_HOME/.codex/agents"

if [[ -e "$SKILL_DEST" && "$FORCE" -ne 1 ]]; then
  echo "Refusing to replace existing skill at $SKILL_DEST" >&2
  echo "Re-run with --force if replacement is intentional." >&2
  exit 1
fi

mkdir -p "$(dirname "$SKILL_DEST")" "$AGENT_DEST"
rm -rf "$SKILL_DEST"
mkdir -p "$SKILL_DEST"
cp "$ROOT/SKILL.md" "$SKILL_DEST/SKILL.md"
cp -R "$ROOT/agents" "$SKILL_DEST/agents"
cp -R "$ROOT/references" "$SKILL_DEST/references"

for src in "$ROOT"/templates/codex-agents/*.toml; do
  dest="$AGENT_DEST/$(basename "$src")"
  if [[ -e "$dest" && "$FORCE" -ne 1 ]]; then
    echo "Skipping existing agent: $dest"
    continue
  fi
  cp "$src" "$dest"
done

echo "Installed runtime skill: $SKILL_DEST"
echo "Installed/updated agent profiles: $AGENT_DEST"
