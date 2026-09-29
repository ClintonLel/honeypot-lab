@AGENTS.md

- Regeln, die für alle Agenten gelten, in AGENTS.md eintragen, nicht hier.
- `.env`-Dateien auch nicht per Bash lesen (`cat`, `grep`, `source` usw.): Die Deny-Regeln in `.claude/settings.json` gelten nur für das Read-Tool.
- Gemeinsame Einstellungen in `.claude/settings.json`, persönliche in `.claude/settings.local.json` (git-ignoriert).
