@AGENTS.md

- Regeln, die für alle Agenten gelten, in AGENTS.md eintragen, nicht hier.
- Nichts, was `.claude/settings.json` unter `deny` sperrt, per Bash lesen oder auswerten: `.env`-Dateien, Keys, Dumps, Logs, Honeypot-Rohdaten (`cowrie.json*`, `tty/`, `downloads/`) und OpenTofu-State, -Pläne und -Variablen. Die Regeln greifen für Read, Grep, Glob und einfache Befehle wie `cat` oder `head`, aber nicht für `grep -r`, `source`, `tofu show` oder Skripte, die Dateien selbst öffnen.
- Gemeinsame Einstellungen in `.claude/settings.json`, persönliche in `.claude/settings.local.json` (git-ignoriert).
