# Abfuhrkalender Berlin

Jahresübersicht der Müllabfuhrtermine für eine beliebige Berliner Adresse – als kleine Web-App fürs Heimnetz. Sie läuft überall, wo es Docker gibt: auf einem NAS (Synology, QNAP, Unraid …), einem Raspberry Pi oder einem Server.

- **Hausmüll, Biogut, Wertstoffe (gelbe Tonne)** – automatisch von der BSR, inkl. Feiertagsverschiebungen. Wertstoffe, die ALBA abholt, kommen ebenfalls über die BSR.
- **Papier (Berlin Recycling)** – entweder per Login ins Kundenportal (für Eigentümer/Verwaltungen) oder als selbst angegebener Turnus.
- Button „Daten aktualisieren“, zusätzlich automatischer Abruf (Standard: wöchentlich).
- Kalender-Abo (`.ics`) fürs Handy, optional mit Erinnerung am Vorabend.
- Druckansicht A4 quer.
- Als App aufs iPhone (Home-Bildschirm), mit Push-Erinnerung am Vorabend; zeigt ohne Serververbindung den zuletzt geladenen Stand.

Die Adresse wird in der App eingerichtet und nur lokal in `data/config.json` gespeichert – im Code steht keine Adresse.

> **Kein offizielles Angebot.** Dies ist ein Freizeitprojekt und steht in keiner Verbindung zur Berliner Stadtreinigung (BSR), zu ALBA oder zu Berlin Recycling. Es nutzt nur Daten, die dort ohnehin abrufbar sind. Alle Angaben ohne Gewähr – maßgeblich sind die Termine der Entsorger.

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

## Betrieb mit Docker

Die App wird als Docker-Container gebaut und gestartet (`Dockerfile`, `docker-compose.yml`). Das klappt auf jedem Rechner mit **Docker** und **Docker Compose** – NAS, Raspberry Pi (64 Bit), Mini-PC oder Server. Ausprobiert ist sie bisher auf einer Synology DS723+ (Anleitung dafür [weiter unten](#beispiel-synology-container-manager)).

### Allgemein (jeder Rechner mit Docker)

Per Terminal bzw. SSH auf dem Rechner:

```bash
git clone https://github.com/ThePhanThomas/abfuhrkalender-berlin.git abfuhrkalender
cd abfuhrkalender && mkdir data && cp .env.example .env && id
```

- Den Ordner `data` **selbst** anlegen (wie oben). Sonst legt Docker ihn mit Administrator-Rechten (`root`) an und die App kann dort nicht speichern.
- `.env` mit einem Texteditor ausfüllen:
  - `PUID`/`PGID`: die Zahlen hinter `uid=` und `gid=` aus der Ausgabe von `id` (auf vielen Linux-Rechnern `1000`, auf der Synology oft `1026` und `100`).
  - `BR_USERNAME`/`BR_PASSWORD`: Login fürs Kundenportal, falls gewünscht. **Jedes `$` doppelt schreiben (`$$`)** – Docker hält `$` sonst für einen Platzhalter und schneidet das Passwort stillschweigend ab; der Login scheitert dann mit „Zugangsdaten prüfen“. Keine Anführungszeichen verwenden. (Nur in der `.env` für Docker; beim lokalen Start ohne Docker bleibt das einfache `$`.)

Starten (der erste Build dauert ein paar Minuten):

```bash
docker compose up -d --build
```

Danach ist die App unter `http://<IP-des-Rechners>:8080` erreichbar. Termine und Einstellungen liegen in `data/` und überleben Updates. Je nach System braucht `docker` ein vorangestelltes `sudo`.

**Ändern und aktualisieren:**

- **Neuer Code:** `git pull` im Projektordner, dann `docker compose up -d --build`.
- **`.env` geändert:** Ein Neustart reicht nicht, der Container muss neu erstellt werden: `docker compose up -d --force-recreate`.
- **Prüfen, ob die Zugangsdaten richtig ankommen** (zeigt nur die Länge, nicht den Wert):
  ```bash
  docker exec abfuhrkalender python -c "import os; p=os.environ.get('BR_PASSWORD',''); print('Länge Passwort:', len(p))"
  ```

Der Container startet nach einem Neustart des Rechners von selbst wieder (`restart: unless-stopped`). Ein anderer Port als 8080 lässt sich in `docker-compose.yml` einstellen (`ports`, linke Zahl).

### Beispiel: Synology (Container Manager)

Läuft auf einer DS723+ mit DSM 7.2 und dem Paket **Container Manager**. Andere Modelle, auf denen der Container Manager läuft (meist „+“-Modelle), sollten genauso funktionieren.

#### Einmalig vorbereiten

1. **Paket-Zentrum:** **Container Manager** (legt den freigegebenen Ordner `docker` an), **Git Server** (liefert das Programm `git`, sonst nichts einrichten) und **Text-Editor** installieren.
2. **Systemsteuerung → Terminal & SNMP:** SSH-Dienst aktivieren. Der eigene NAS-Benutzer muss zur Gruppe „administrators“ gehören.

#### Code aufs NAS holen

Per SSH auf dem NAS (`ssh <benutzer>@<NAS-IP>`):

```bash
cd /volume1/docker && git clone https://github.com/ThePhanThomas/abfuhrkalender-berlin.git abfuhrkalender
```

Das Repo ist öffentlich, dafür braucht es kein GitHub-Konto und keinen Schlüssel.

#### Einrichten

```bash
cd /volume1/docker/abfuhrkalender && mkdir data && cp .env.example .env && id
```

`.env` dann in der File Station mit dem Text-Editor öffnen und wie [oben beschrieben](#allgemein-jeder-rechner-mit-docker) ausfüllen.

#### Starten

Container Manager → **Projekt** → **Erstellen**:

- Projektname: `abfuhrkalender`, Pfad: `/docker/abfuhrkalender`, Quelle: „Vorhandene docker-compose.yml verwenden“
- „Webportal via Web Station einrichten“: **nicht** anhaken (nicht nötig).
- „Projekt nach der Erstellung starten“ anhaken, Fertig.

Der erste Build dauert ein paar Minuten. Meldet der Container Manager dabei „Projekt konnte nicht erstellt werden“, lief der Build bei uns trotzdem im Hintergrund weiter – erst ein paar Minuten warten und `http://<NAS-IP>:8080` aufrufen. Den echten Fehler sieht man per SSH mit `cd /volume1/docker/abfuhrkalender && sudo docker compose build`.

#### Ändern und aktualisieren

Wie [oben](#allgemein-jeder-rechner-mit-docker), per SSH im Ordner `/volume1/docker/abfuhrkalender` und mit `sudo` vor `docker`. Statt `docker compose up -d --build` geht auch: im Container Manager beim Projekt „Erstellen“ (Build) und neu starten.

## Als App aufs iPhone (mit Push-Erinnerung)

Damit das iPhone die App mit Symbol, Push-Erinnerungen und Anzeige ohne Server erlaubt, muss sie über **HTTPS** laufen, mit einem Zertifikat, dem das Gerät vertraut (ein selbst signiertes reicht nicht). Über `http://<IP>:8080` geht das nicht – die App funktioniert dort weiter, nur ohne diese Extras.

### HTTPS einrichten

Wie man dahin kommt, hängt vom eigenen Netz ab. Die App braucht nur eine HTTPS-Adresse, die an Port 8080 weiterleitet. Gängige Wege:

- **Eigene Domain mit Reverse Proxy:** Ein Name wie `kalender.<deine-domain>` zeigt im DNS auf die Heimnetz-Adresse des Servers. Ein Reverse Proxy nimmt dort HTTPS an und reicht an Port 8080 weiter – auf der Synology unter Systemsteuerung → Anmeldeportal → Erweitert → Reverse Proxy, sonst z. B. Caddy, nginx oder Traefik. Das Zertifikat kommt von Let's Encrypt über eine DNS-Prüfung, etwa mit [acme.sh](https://github.com/acmesh-official/acme.sh) und dem Modul für den eigenen Domain-Anbieter ([Anleitung für die Synology](https://github.com/acmesh-official/acme.sh/wiki/Synology-NAS-Guide)). Am Router muss nichts freigegeben werden; von unterwegs ist die App nur per VPN ins Heimnetz live.
- **Tailscale:** `tailscale serve --bg 8080` gibt dem Server eine Adresse `https://<rechnername>.<tailnet>.ts.net` mit Zertifikat ([Anleitung](https://tailscale.com/kb/1312/serve)). Die Adresse ist nur erreichbar, solange Tailscale auch auf dem iPhone läuft – dann aber auch unterwegs.
- **Vorhandener Reverse Proxy:** Wer schon einen mit gültigem Zertifikat betreibt, leitet einen Namen an Port 8080 weiter.

Zeigt ein öffentlicher Name auf eine Heimnetz-Adresse, blockieren manche Router ihn vorsorglich (**DNS-Rebind-Schutz**). Dann den Namen dort als Ausnahme eintragen, bei der Fritz!Box unter Heimnetz → Netzwerk → Netzwerkeinstellungen.

### Auf dem iPhone (iOS 16.4 oder neuer)

1. In **Safari** die HTTPS-Adresse öffnen → Teilen-Symbol (ggf. hinter „…“) → **Zum Home-Bildschirm** („Als Web-App öffnen“ anlassen).
2. Die App über das neue Symbol öffnen → **Einstellungen** → „Erinnerung per Push“ einschalten, Mitteilungen erlauben, **Test senden**.

Gut zu wissen:

- Ist der Server nicht erreichbar (z. B. unterwegs ohne VPN), zeigt die App den zuletzt geladenen Stand mit einem Hinweis. Aktualisieren, Einstellungen und „Test senden“ gehen dann nicht.
- Push-Erinnerungen kommen trotzdem: Der Server schickt sie über Apple an das iPhone, das iPhone muss den Server dafür nicht erreichen.
- Die App gehört zu ihrer Adresse. Ändert sich die Adresse (z. B. beim Wechsel von Tailscale auf eine eigene Domain), die alte App vom Home-Bildschirm löschen, die neue hinzufügen und Push dort neu einschalten. Einstellungen pro Gerät (ausgeblendete Müllarten, Hell/Dunkel) müssen dann neu gesetzt werden.
- Die Uhrzeit (Standard 18 Uhr) gilt für alle Geräte; ein- und ausgeschaltet wird pro Gerät. Erinnert wird nur, wenn am nächsten Tag eine der angezeigten Müllarten abgeholt wird.
- Zusätzlich kommen Hinweise (nur zwischen 8 und 21 Uhr): etwa eine Woche vorher, wenn ein Termin verschoben ist (z. B. wegen eines Feiertags); wenn sich beim Abruf ein Termin der nächsten zwei Wochen geändert hat; und wenn der Abruf einer Quelle zweimal hintereinander fehlschlägt (und wieder, sobald er klappt). Nach einem Fehlschlag versucht die App es nach 6 Stunden erneut.
- Jedes Gerät meldet sich einzeln an. Wird die App vom Home-Bildschirm gelöscht, entfernt der Server die Anmeldung beim nächsten Versand von selbst.

## Konfiguration (`.env`)

| Variable | Bedeutung |
|---|---|
| `BR_USERNAME`, `BR_PASSWORD` | Login Kundenportal Berlin Recycling (nur für Papier-Modus „Kundenportal“). Für Docker jedes `$` als `$$` schreiben. |
| `REFRESH_INTERVAL_HOURS` | Automatischer Abruf in Stunden, `0` = nur per Button (Standard `168`) |
| `DATA_DIR` | Speicherort für `config.json`/`pickups.json` (Standard `data`, im Container `/data`) |
| `PUID`, `PGID` | Benutzer-/Gruppennummer, unter der der Container läuft; muss zum Besitzer von `data/` passen (Standard `1000`) |
| `PUSH_ENABLED` | `0` schaltet den Versand der Push-Erinnerungen ab (Standard `1`) |
| `VAPID_SUBJECT` | Absenderangabe für Push (`mailto:` oder `https:`), optional. Standard ist eine Platzhalter-Adresse. |
| `VAPID_PRIVATE_KEY` | Optional. Schlüssel des Servers für Push (PEM). Ohne Angabe erzeugt die App einen und speichert ihn in `data/vapid.json` – dann nicht löschen, sonst müssen alle Geräte Push neu einschalten. |

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
  push.py               Push-Erinnerung und Hinweise (Schlüssel, Anmeldungen, Versand)
  sources/bsr.py        BSR (Adresssuche + Termine)
  sources/berlin_recycling.py  Kundenportal
  sources/manual.py     Papier-Turnus von Hand
  static/               Oberfläche (HTML/CSS/JS, kein Build-Schritt)
  static/sw.js          Service Worker: Anzeige ohne Server, Push (unter /sw.js ausgeliefert)
tools/make_icons.py     erzeugt die PNG-Icons aus static/icon.svg (braucht Chrome)
tests/                  pytest, alle Webcalls gemockt
```

## Lizenz

[MIT](LICENSE) – der Code darf frei genutzt, verändert und weitergegeben werden, solange der Lizenzhinweis erhalten bleibt. Die verwendeten Python-Bibliotheken (siehe `requirements.txt`) stehen unter ihren eigenen, ebenfalls freien Lizenzen.
