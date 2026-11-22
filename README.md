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

Läuft auf einer DS723+ mit DSM 7.2 und dem Paket **Container Manager**. Andere Modelle, auf denen der Container Manager läuft (meist „+“-Modelle), sollten genauso funktionieren.

### Einmalig vorbereiten

1. **Paket-Zentrum:** **Container Manager** (legt den freigegebenen Ordner `docker` an), **Git Server** (liefert das Programm `git`, sonst nichts einrichten) und **Text-Editor** installieren.
2. **Systemsteuerung → Terminal & SNMP:** SSH-Dienst aktivieren. Der eigene NAS-Benutzer muss zur Gruppe „administrators“ gehören.
3. **Systemsteuerung → Benutzer und Gruppe → Erweitert:** „Benutzer-Home-Dienst aktivieren“ (dort liegt der SSH-Schlüssel).

### Code aufs NAS holen (Deploy-Key)

Das Repo ist privat. Ein Zugangs-Token ließ sich auf GitHub nicht anlegen (der Button „Generate token“ reagierte nicht), deshalb nutzen wir einen **Deploy-Key**: ein Schlüsselpaar, das das NAS erzeugt und das bei GitHub nur für dieses Repo und nur zum Lesen hinterlegt ist.

Per SSH auf dem NAS (`ssh <benutzer>@<NAS-IP>`):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh && ssh-keygen -t ed25519 -f ~/.ssh/abfuhrkalender -N "" -C "synology-abfuhrkalender"
printf 'Host github-abfuhrkalender\n  HostName github.com\n  User git\n  IdentityFile ~/.ssh/abfuhrkalender\n  IdentitiesOnly yes\n' >> ~/.ssh/config && chmod 600 ~/.ssh/config
cat ~/.ssh/abfuhrkalender.pub
```

Die ausgegebene Zeile (`ssh-ed25519 …`) auf GitHub im Repo unter **Settings → Deploy keys → Add deploy key** einfügen, **ohne** „Allow write access“. Dann:

```bash
ssh -T github-abfuhrkalender   # beim ersten Mal Fingerabdruck prüfen: SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU
cd /volume1/docker && git clone github-abfuhrkalender:<github-benutzer>/abfuhrkalender-berlin.git abfuhrkalender
```

### Einrichten

```bash
cd /volume1/docker/abfuhrkalender && mkdir data && cp .env.example .env && id
```

- Den Ordner `data` **selbst** anlegen (wie oben). Sonst legt Docker ihn mit Administrator-Rechten an und die App kann dort nicht speichern.
- `.env` in der File Station mit dem Text-Editor öffnen und ausfüllen:
  - `PUID`/`PGID`: die Zahlen hinter `uid=` und `gid=` aus der Ausgabe von `id` (z. B. `1026` und `100`).
  - `BR_USERNAME`/`BR_PASSWORD`: Login fürs Kundenportal, falls gewünscht. **Jedes `$` doppelt schreiben (`$$`)** – Docker hält `$` sonst für einen Platzhalter und schneidet das Passwort stillschweigend ab; der Login scheitert dann mit „Zugangsdaten prüfen“. Keine Anführungszeichen verwenden. (Nur in der `.env` für Docker; lokal auf dem Mac bleibt das einfache `$`.)

### Starten

Container Manager → **Projekt** → **Erstellen**:

- Projektname: `abfuhrkalender`, Pfad: `/docker/abfuhrkalender`, Quelle: „Vorhandene docker-compose.yml verwenden“
- „Webportal via Web Station einrichten“: **nicht** anhaken (nicht nötig).
- „Projekt nach der Erstellung starten“ anhaken, Fertig.

Der erste Build dauert ein paar Minuten. Meldet der Container Manager dabei „Projekt konnte nicht erstellt werden“, lief der Build bei uns trotzdem im Hintergrund weiter – erst ein paar Minuten warten und `http://<NAS-IP>:8080` aufrufen. Den echten Fehler sieht man per SSH mit `cd /volume1/docker/abfuhrkalender && sudo docker compose build`.

Danach ist die App unter `http://<NAS-IP>:8080` erreichbar. Die Termine und Einstellungen liegen in `data/` und überleben Updates.

### Ändern und aktualisieren

- **`.env` geändert:** Ein Neustart reicht nicht, der Container muss neu erstellt werden:
  ```bash
  cd /volume1/docker/abfuhrkalender && sudo docker compose up -d --force-recreate
  ```
- **Neuer Code:** `git pull` im Projektordner, dann im Container Manager beim Projekt „Erstellen“ (Build) und neu starten – oder per SSH `sudo docker compose up -d --build`.
- **Prüfen, ob die Zugangsdaten richtig ankommen** (zeigt nur Längen, nicht die Werte):
  ```bash
  sudo docker exec abfuhrkalender python -c "import os; p=os.environ.get('BR_PASSWORD',''); print('Länge Passwort:', len(p))"
  ```

## Konfiguration (`.env`)

| Variable | Bedeutung |
|---|---|
| `BR_USERNAME`, `BR_PASSWORD` | Login Kundenportal Berlin Recycling (nur für Papier-Modus „Kundenportal“). Für Docker jedes `$` als `$$` schreiben. |
| `REFRESH_INTERVAL_HOURS` | Automatischer Abruf in Stunden, `0` = nur per Button (Standard `168`) |
| `DATA_DIR` | Speicherort für `config.json`/`pickups.json` (Standard `data`, im Container `/data`) |
| `PUID`, `PGID` | Benutzer-/Gruppennummer, unter der der Container läuft; muss zum Besitzer von `data/` passen (Standard `1000`) |

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
