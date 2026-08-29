# Contributing

Keep changes small and preserve the v1 invariants in `manifest.toml`, `SKILL.md`, and `references/`.

Before opening a change, run:

```text
python -m unittest discover -s tests -p 'test_*.py' -v
python scripts/verify.py
bash -n scripts/install-codex.sh
git diff --check
```

Changes to delegation, model/effort defaults, installer ownership, or release packaging must add or update regression tests. Do not add new Agent roles unless a recurring repository ownership boundary cannot be represented by the existing roles.
