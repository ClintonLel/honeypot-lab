# Workflow-Log

Eine Zeile je abgeschlossener Aufgabe, neueste unten.

- Werkzeug: Claude Code, Cursor o. Ä., mit Modell
- Schritt: Nummer aus dem Bauplan, sonst –
- Ergebnis: fertig, offen oder verworfen
- Nacharbeit: was von Hand korrigiert wurde, sonst –

| Datum | Werkzeug | Schritt | Aufgabe | Ergebnis | Nacharbeit | Commit |
|-------|----------|---------|---------|----------|------------|--------|
| 29.09. | #2 AGENTS.md honeypot-lab | Claude Code / Antigravity (Gemini Pro), Review erst nach Merge | – | ja, Fix-PR #3 | ~10 Befunde, ~7 echt, 2–3 Fehlalarme | – |
| 29.09. | Review ci/tests (zu früh gestartet) | – / Antigravity | – | ja | Branch fehlte; 57 Befehle statt Abbruch, Home-Verzeichnis durchsucht → Abbruchregel im Prompt, Terminal-Freigabe auf Nachfragen | – |
