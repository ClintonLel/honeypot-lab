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
| 29.09. | 6.1 ATT&CK-Regeln (#5) | Claude Code / Antigravity (Gemini), Befunde gegengeprüft von Claude (Projekt) | – | ja, 1 Runde (0a912d9) | 4 Befunde: 2 echt (ReDoS-Prüfung ließ überlappende Alternativen durch; `then sudo …` und `/bin/sudo …` ohne Tag), 2 Fehlalarme (`NULL` in `commands.techniques`, Spalte ist seit 0001 NOT NULL). Antigravity legte 3 Hilfsdateien im Repo ab → Prompt: „keine Dateien anlegen“. Report-Ausgabe lief in den Claude-Code-Chat → Server-Befehle künftig im eigenen Terminal | – |
| 29.09. | 6.1 Folge-PR Regeln (#7) | Claude Code / Antigravity (Gemini), Stichprobe Claude (Projekt) | – | nein | 0 Befunde; deckt sich mit Claudes Stichprobe (23 Befehle, ReDoS-Worst-Case 12,8 ms). Antigravity ließ pytest lokal auf dem falschen Stand laufen (301 statt 378 Tests, vermutlich `main`) und legte dafür `.venv` an → Prompt: „Tests nicht ausführen, das macht die CI“ | – |
| 30.09. | 6.2 Kampagnen (#8) | Claude Code / Antigravity (Gemini); Plan und Befunde geprüft von Claude (Projekt) | – | nein | Plan: 3 Ergänzungen von Claude (p3-Spalte im Bericht, `lock_timeout`, Grenze „verschiedene URLs = eine Kampagne“ dokumentieren), alle umgesetzt. Review: 2 Befunde, 0 echt: 1 Fehlalarm (RFC-5737-Dokuadresse im `X-Forwarded-For` eines Tests, gleiche Konvention wie in 7 anderen Testdateien, keine Angreiferadresse), 1 berechtigt, aber gering (`run campaigns --bericht` ohne End-zu-End-Test; Bericht und Formatierung einzeln getestet, gleicher Stand wie bei `attack`) → nicht nachgebessert. Antigravity legte trotz Prompt `diff.patch` und `scratch.py` an (per `>`-Umleitung) und wechselte mit `git switch` den Branch im Arbeitsordner → Prompt: keine Umleitung in Dateien, Branch nicht wechseln | – |
