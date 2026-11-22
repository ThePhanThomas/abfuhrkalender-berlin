# Abfuhrkalender Berlin

Jahresübersicht der Müllabfuhrtermine für eine beliebige Berliner Adresse – als kleine Web-App fürs Heimnetz (z. B. auf einer Synology).

- **Hausmüll, Biogut, Wertstoffe (gelbe Tonne)** – automatisch von der BSR, inkl. Feiertagsverschiebungen. Wertstoffe, die ALBA abholt, kommen ebenfalls über die BSR.
- **Papier (Berlin Recycling)** – entweder per Login ins Kundenportal (für Eigentümer/Verwaltungen) oder als selbst angegebener Rhythmus.
- Button „Daten aktualisieren“, zusätzlich automatischer Abruf (Standard: wöchentlich).
- Kalender-Abo (`.ics`) fürs Handy, optional mit Erinnerung am Vorabend.
- Druckansicht A4 quer.

Die Adresse wird in der App eingerichtet und nur lokal in `data/config.json` gespeichert – im Code steht keine Adresse.

## Lokal starten (Mac/Linux)

Voraussetzung: [uv](https://docs.astral.sh/uv/) oder Python 3.12.

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv -r requirements-dev.txt
cp .env.example .env   # optional: Zugangsdaten Berlin Recycling eintragen
.venv/bin/uvicorn app.main:app --reload --port 8080 --env-file .env
```

Dann <http://localhost:8080> öffnen. Beim ersten Start fragt die App nach der Adresse.

Tests:

```bash
.venv/bin/python -m pytest -q
```

## Betrieb auf der Synology (Container Manager)

Getestet für DSM 7.2+ mit dem Paket **Container Manager**.

1. In der File Station einen Ordner anlegen, z. B. `/docker/abfuhrkalender`.
2. Den Inhalt dieses Repos dorthin kopieren (oder per SSH `git clone`).
3. Dort `.env.example` nach `.env` kopieren und ausfüllen (Zugangsdaten Berlin Recycling, falls gewünscht).
4. Container Manager → **Projekt** → **Erstellen**:
   - Projektname: `abfuhrkalender`
   - Pfad: der Ordner aus Schritt 1
   - Quelle: „Vorhandene docker-compose.yml verwenden“
5. Projekt starten. Die App ist danach unter `http://<NAS-IP>:8080` erreichbar.

Die Termine und Einstellungen liegen im Unterordner `data/` und überleben Updates.

**Update nach Code-Änderungen:** neuen Stand in den Ordner holen (`git pull`), dann im Container Manager beim Projekt „Erstellen“ (Build) und neu starten.

## Konfiguration (`.env`)

| Variable | Bedeutung |
|---|---|
| `BR_USERNAME`, `BR_PASSWORD` | Login Kundenportal Berlin Recycling (nur für Papier-Modus „Kundenportal“) |
| `REFRESH_INTERVAL_HOURS` | Automatischer Abruf in Stunden, `0` = nur per Button (Standard `168`) |
| `DATA_DIR` | Speicherort für `config.json`/`pickups.json` (Standard `data`, im Container `/data`) |

## Datenquellen

| Quelle | Endpunkt | Hinweise |
|---|---|---|
| BSR | `umnewforms.bsr.de/p/de.bsr.adressen.app/…` | Öffentlich, aber undokumentiert. Blockt Aufrufe direkt aus dem Browser (CORS/403) – deshalb läuft der Abruf über den Server. |
| Berlin Recycling | `kundenportal.berlin-recycling.de` | Login nötig. Liefert nur die nächsten ~10 Termine; bereits abgerufene vergangene Termine bewahrt die App auf. Der öffentliche Mieter-Kalender ist per reCAPTCHA geschützt und wird bewusst **nicht** automatisiert. |

Beide Schnittstellen können sich ohne Ankündigung ändern. Schlägt ein Abruf fehl, bleiben die zuletzt geladenen Termine erhalten und die App zeigt einen Hinweis.

## Aufbau

```
app/
  main.py               FastAPI: Seite + JSON-API
  refresh.py            ruft alle Quellen ab, speichert Ergebnis
  store.py              config.json / pickups.json
  ics.py                Kalender-Export
  sources/bsr.py        BSR (Adresssuche + Termine)
  sources/berlin_recycling.py  Kundenportal
  sources/manual.py     Papier-Rhythmus von Hand
  static/               Oberfläche (HTML/CSS/JS, kein Build-Schritt)
tests/                  pytest, alle Webcalls gemockt
```
