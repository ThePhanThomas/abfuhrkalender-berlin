# Abfuhrkalender Berlin

Jahresübersicht der Müllabfuhrtermine für eine beliebige Berliner Adresse – als kleine Web-App fürs Heimnetz (z. B. auf einer Synology).

- **Hausmüll, Biogut, Wertstoffe (gelbe Tonne)** – automatisch von der BSR, inkl. Feiertagsverschiebungen. Wertstoffe, die ALBA abholt, kommen ebenfalls über die BSR.
- **Papier (Berlin Recycling)** – entweder per Login ins Kundenportal (für Eigentümer/Verwaltungen) oder als selbst angegebener Turnus.
- Button „Daten aktualisieren“, zusätzlich automatischer Abruf (Standard: wöchentlich).
- Kalender-Abo (`.ics`) fürs Handy, optional mit Erinnerung am Vorabend.
- Druckansicht A4 quer.
- Als App aufs iPhone (Home-Bildschirm), mit Push-Erinnerung am Vorabend; zeigt ohne Serververbindung den zuletzt geladenen Stand.

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

## Als App aufs iPhone (mit Push-Erinnerung)

Damit das iPhone die App mit Symbol, Push-Erinnerungen und Anzeige ohne Server erlaubt, muss sie über **HTTPS** mit einem gültigen Zertifikat laufen. Über `http://<NAS-IP>:8080` geht das nicht (die App funktioniert dort weiter, nur ohne diese Extras). Wir nutzen dafür **Tailscale**: Es gibt dem NAS eine feste HTTPS-Adresse (`https://<nas-name>.<tailnet>.ts.net`) mit Zertifikat, ohne dass am Router etwas freigegeben werden muss.

### Einmalig auf der Synology

1. **Paket-Zentrum:** **Tailscale** installieren, öffnen und mit einem (kostenlosen) Tailscale-Konto anmelden.
2. In der Tailscale-Verwaltung im Browser (<https://login.tailscale.com/admin/dns>): **MagicDNS** einschalten und darunter **HTTPS Certificates** aktivieren.
3. Per SSH auf dem NAS die App über HTTPS freigeben (leitet auf Port 8080 weiter, bleibt nach einem Neustart erhalten):
   ```bash
   sudo /var/packages/Tailscale/target/bin/tailscale serve --bg 8080
   ```
   Die Ausgabe zeigt die Adresse `https://<nas-name>.<tailnet>.ts.net`. Abschalten mit `… tailscale serve --https=443 off`.
4. **Lädt die HTTPS-Adresse endlos** (bei uns beim ersten Mal passiert), während `http://<nas-name>.<tailnet>.ts.net:8080` geht: Das Zertifikat einmal von Hand holen, danach ging es sofort. Die Dateien landen in `/tmp` und werden nicht gebraucht (die `.key`-Datei ist geheim, also löschen):
   ```bash
   cd /tmp && sudo /var/packages/Tailscale/target/bin/tailscale cert <nas-name>.<tailnet>.ts.net && sudo rm <nas-name>.<tailnet>.ts.net.crt <nas-name>.<tailnet>.ts.net.key
   ```

### Auf dem iPhone (iOS 16.4 oder neuer)

1. App **Tailscale** aus dem App Store installieren, mit demselben Konto anmelden, VPN einschalten.
2. In **Safari** die Adresse `https://<nas-name>.<tailnet>.ts.net` öffnen → Teilen-Symbol (ggf. hinter „…“) → **Zum Home-Bildschirm** („Als Web-App öffnen“ anlassen).
3. Die App über das neue Symbol öffnen → **Einstellungen** → „Erinnerung per Push“ einschalten, Mitteilungen erlauben, **Test senden**.

Gut zu wissen:

- Die `ts.net`-Adresse funktioniert nur, solange Tailscale auf dem iPhone an ist – zu Hause **und unterwegs**. Mit Tailscale ist die App also überall live.
- Ist Tailscale aus oder das NAS nicht erreichbar, zeigt die App den zuletzt geladenen Stand mit einem blauen Hinweis. Aktualisieren und Einstellungen gehen dann nicht.
- Push-Erinnerungen kommen immer, auch ohne Tailscale: Der Server schickt sie über Apple an das iPhone.
- Die Uhrzeit (Standard 18 Uhr) gilt für alle Geräte; ein- und ausgeschaltet wird pro Gerät. Erinnert wird nur, wenn am nächsten Tag eine der angezeigten Müllarten abgeholt wird.
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
  push.py               Push-Erinnerung (Schlüssel, Anmeldungen, Versand)
  sources/bsr.py        BSR (Adresssuche + Termine)
  sources/berlin_recycling.py  Kundenportal
  sources/manual.py     Papier-Turnus von Hand
  static/               Oberfläche (HTML/CSS/JS, kein Build-Schritt)
  static/sw.js          Service Worker: Anzeige ohne Server, Push (unter /sw.js ausgeliefert)
tools/make_icons.py     erzeugt die PNG-Icons aus static/icon.svg (braucht Chrome)
tests/                  pytest, alle Webcalls gemockt
```
