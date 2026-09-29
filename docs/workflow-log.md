# Workflow-Log

Eine Zeile je abgeschlossener Aufgabe, neueste unten.

- Schritt: Nummer aus dem Bauplan oder PR/Aufgabe
- Tool (baut / prüft): Werkzeug mit Modell, das baut / das reviewt, sonst –
- Dauer: ungefähr, sonst –
- Nacharbeit nötig?: ja oder nein, bei ja womit
- Was das Review gefunden hat: Befunde, davon echt und Fehlalarme
- Kontingent/Kosten: verbrauchtes Kontingent oder Kosten, sonst –

| Datum | Schritt | Tool (baut / prüft) | Dauer | Nacharbeit nötig? | Was das Review gefunden hat | Kontingent/Kosten |
|-------|---------|---------------------|-------|-------------------|-----------------------------|-------------------|
| 29.09. | #2 AGENTS.md honeypot-lab | Claude Code / Antigravity (Gemini Pro), Review erst nach Merge | – | ja, Fix-PR #3 | ~10 Befunde, ~7 echt, 2–3 Fehlalarme | – |
| 29.09. | Review ci/tests (zu früh gestartet) | – / Antigravity | – | ja | Branch fehlte; 57 Befehle statt Abbruch, Home-Verzeichnis durchsucht → Abbruchregel im Prompt, Terminal-Freigabe auf Nachfragen | – |
