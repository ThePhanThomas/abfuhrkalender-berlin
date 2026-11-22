# CLAUDE.md

Hinweise für Claude (und Menschen), die an diesem Repository arbeiten.

## Worum es geht

Eine kleine Web-App, die die Müllabfuhrtermine für eine Berliner Adresse als Jahreskalender zeigt. Sie läuft im Heimnetz als Docker-Container auf einer Synology. Mehr dazu im [README](README.md).

**Zu Beginn jeder Session [docs/STATUS.md](docs/STATUS.md) lesen** – dort stehen der aktuelle Stand, offene Punkte und bekannte Stolpersteine. Wer etwas abschließt oder Neues herausfindet, aktualisiert die Datei im selben Pull Request.

## Zusammenarbeit

- Mehrere Personen arbeiten hier mit, nicht alle sind Entwickler. **Antworte auf Deutsch**, erkläre Schritte verständlich und ohne unnötigen Fachjargon. Wenn ein Fachbegriff nötig ist, erkläre ihn kurz.
- Frag nach, bevor du etwas Größeres umbaust, Abhängigkeiten hinzufügst oder das Aussehen der App deutlich veränderst. Kleine, klar umrissene Änderungen sind besser als große.
- Arbeite auf einem eigenen Branch (z. B. `feature/erinnerung-per-mail`), nicht direkt auf `main`. Änderungen kommen per Pull Request auf `main`; die Tests laufen dort automatisch (GitHub Actions).
- Commit-Nachrichten auf Deutsch, kurz und im Imperativ: „Druckansicht für A5 ergänzen“.
- Nichts pushen, mergen oder löschen, ohne dass die Person es ausdrücklich möchte.

## Feste Regeln

1. **Keine persönlichen Daten im Code.** Keine Adressen, BSR-Adressschlüssel (`AddrKey`), Namen oder Zugangsdaten in Code, Tests, Commits oder Doku. Die Adresse wird in der App eingerichtet und landet nur in `data/config.json` (per `.gitignore` ausgeschlossen). Testdaten sind erfunden („Musterstr. 1A“).
2. **Geheimnisse nur in `.env`.** Zugangsdaten (z. B. `BR_USERNAME`/`BR_PASSWORD`) kommen ausschließlich aus Umgebungsvariablen. Sie werden nie in `data/` gespeichert, nie geloggt und nie an die Oberfläche geschickt. `.env` und `data/` niemals committen.
3. **Keine Schutzmechanismen umgehen.** Der öffentliche Mieter-Kalender von Berlin Recycling ist per reCAPTCHA geschützt – den nicht automatisieren. Nur die Schnittstellen nutzen, die ohne Tricks funktionieren (BSR-API, Kundenportal mit eigenem Login).
4. **Tests machen keine echten Webcalls.** Externe Aufrufe werden mit `httpx.MockTransport` simuliert (siehe `tests/conftest.py`). Der Push-Versand (`push.webpush`) ist in Tests gesperrt; wer ihn testet, ersetzt ihn (Fixture `sent` in `tests/test_push.py`). Neue Funktionen bekommen Tests.
5. **Ein Ausfall darf nichts löschen.** Schlägt eine Quelle fehl, bleiben ihre alten Termine erhalten (`app/refresh.py`). Fehlermeldungen für die Oberfläche sind deutsch und verständlich (`SourceError("…")`).

## Entwickeln

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8080 --env-file .env   # http://localhost:8080
.venv/bin/python -m pytest -q                         # Tests
```

Vor jedem Commit die Tests laufen lassen. Bei Änderungen an der Oberfläche die App starten und im Browser ansehen (hell und dunkel, schmales Fenster, Druckvorschau).

## Aufbau und Konventionen

- **Backend:** Python 3.12, FastAPI, httpx. Code und Bezeichner auf Englisch, alles, was Nutzer sehen, auf Deutsch.
- **Frontend:** `app/static/` – reines HTML/CSS/JavaScript ohne Build-Schritt und ohne externe Bibliotheken oder CDNs. So soll es bleiben.
- **Quellen:** Jede Datenquelle ist ein Modul in `app/sources/` mit einer Funktion, die eine Liste von `Pickup` (siehe `app/models.py`) zurückgibt. Eine neue Quelle wird in `app/refresh.py` eingehängt.
- **Müllarten** haben Kürzel (`HM`, `BI`, `WS`, `PP`, …) in `app/models.py`. Die Farben stehen als CSS-Variablen `--c-<Kürzel>` in `app/static/app.css` (hell und dunkel).
- **Daten:** `data/config.json` (Einstellungen), `data/pickups.json` (abgerufene Termine, je Quelle), `data/push.json` (für Push angemeldete Geräte) und `data/vapid.json` (Push-Schlüssel des Servers).
- **PWA:** `app/static/sw.js` (unter `/sw.js` ausgeliefert) speichert Seite und `/api/state` für die Anzeige ohne Server und empfängt Push. Läuft nur über HTTPS – auf dem NAS per Tailscale (README).

## Schnittstellen (Stand November 2026)

- **BSR Adresssuche:** `GET https://umnewforms.bsr.de/p/de.bsr.adressen.app/plzSet/plzSet?searchQuery=<Straße>:::<Hausnr>` – Schreibweise ist tolerant. Ungültige Anfragen liefern eine HTML-Fehlerseite statt JSON.
- **BSR Termine:** `GET …/abfuhrEvents?filter=AddrKey eq '<key>' and DateFrom eq datetime'YYYY-MM-DDT00:00:00' and DateTo eq datetime'…'` – liefert Hausmüll, Bio, Wertstoffe (auch ALBA), Laub, Weihnachtsbäume inkl. Verschiebungen. Anfragen mit `Origin`-Header werden abgelehnt, deshalb nur serverseitig.
- **Berlin Recycling Kundenportal:** Login über `POST /Login.aspx/Auth`, dann `GetDashboard` und `GetDatasetTableHead` mit `datasettablecode: ABFUHRKALENDER`. Antworten sind doppelt JSON-kodiert (`{"d": "<json>"}`). Nach dem Login muss `Default.aspx` einmal per GET aufgerufen werden, sonst liefern die Datenabfragen `{"Error": …}`. Das Portal gibt nur kommende Termine zurück (Felder `Task Date`, `Material Description`); vergangene werden in `app/refresh.py` aus früheren Abrufen aufbewahrt (`keep_past`).

Wenn eine Schnittstelle nicht mehr funktioniert: erst mit `curl` prüfen, was sie jetzt liefert, dann Modul und Tests anpassen und diesen Abschnitt aktualisieren.

## Deployment

Auf der Synology über den Container Manager mit `docker-compose.yml` (siehe README). Nach Änderungen: `git pull` im Projektordner auf dem NAS, dann Projekt neu bauen und starten.
