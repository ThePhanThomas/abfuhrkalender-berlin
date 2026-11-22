# Projektstand und Übergabe

Diese Datei ist für alle – Menschen wie Claude –, die hier in einer neuen Session weiterarbeiten. Sie ergänzt die [CLAUDE.md](../CLAUDE.md) (Regeln und Konventionen) und das [README](../README.md) (Installation und Betrieb) um den **aktuellen Stand**: Was ist fertig, was ist offen, worüber ist man schon gestolpert.

**Bitte aktuell halten:** Wer ein Feature abschließt oder etwas Neues herausfindet, passt diese Datei im selben Pull Request an.

_Stand: 22.11.2026_

---

## Kurz gesagt

Die App läuft im Heimnetz auf der Synology (DS723+, Container Manager) und lokal zum Entwickeln. Alle vier Müllarten kommen automatisch:

| Müllart | Quelle | Status |
|---|---|---|
| Hausmüll, Biogut | BSR-API | ✅ funktioniert, inkl. Feiertagsverschiebungen |
| Wertstoffe (gelbe Tonne) | BSR-API (Abfuhr durch ALBA) | ✅ funktioniert |
| Papier | Berlin Recycling Kundenportal (Login) | ✅ funktioniert mit echtem Login getestet |

Läuft seit 22.11.2026 auf der Synology, alle vier Müllarten werden dort abgerufen.

## Was fertig ist

| Funktion | Wo im Code |
|---|---|
| Einrichtung der Adresse in der App (Suche über BSR, keine Adresse im Code) | `app/static/app.js` (Einstellungen), `app/sources/bsr.py` |
| Jahresübersicht: Abholtage farbig gefüllt (zwei Arten = diagonal geteilt), laufender Monat hervorgehoben, vergangene Monate blasser, Feiertagsverschiebung als roter Punkt | `app/static/app.js` (`renderMonths`) |
| „Nächste Abholung“ als große Karte mit Countdown, übrige Müllarten als Liste daneben; Symbol je Müllart (`CAT_ICONS`) | `app/static/app.js` (`renderNext`, `tile`) |
| App-Icon (Tonne, Kalenderblatt, Fernsehturm), wechselt selbst zwischen hell und dunkel; dient auch als Favicon | `app/static/icon.svg` |
| Info-Kasten pro Abholtag (Maus, Antippen, Tastatur) | `app/static/app.js` (`initTooltip`, `showTip`) |
| Kopfzeile mit App-Icon und Jahres-Umschalter „‹ 2026 ›“, bleibt beim Scrollen oben (durchscheinend) | `app/static/index.html`, `app.css` |
| Button „Aktualisieren“ + automatischer Abruf (Standard wöchentlich) | `app/main.py` (`_auto_refresh_loop`), `app/refresh.py` |
| Papier: Kundenportal **oder** selbst angegebener Rhythmus **oder** aus | `app/sources/berlin_recycling.py`, `app/sources/manual.py` |
| Vergangene Papiertermine bleiben erhalten (Portal liefert nur kommende) | `app/refresh.py` (`keep_past`) |
| Kalender-Abo (`/api/calendar.ics`), optional Erinnerung am Vorabend 18 Uhr | `app/ics.py` |
| Druckansicht als Jahresplaner auf **einer** A4-Seite quer: je Monat eine Spalte mit Platz zum Eintragen, Wochenenden schattiert, Berliner Feiertage, KW, Fußzeile mit Berliner Skyline | `app/static/app.js` (`renderPlanner`, `berlinHolidays`), `app.css` (`@media print`), Fußzeile in `index.html` |
| Helles/dunkles Design, Handy-Layout | `app/static/app.css` |
| Docker-Setup für Synology (läuft auf DS723+), Benutzernummer per `PUID`/`PGID` | `Dockerfile`, `docker-compose.yml`, README |
| Tests (29, alle Webcalls gemockt) + GitHub Actions bei Push/PR | `tests/`, `.github/workflows/tests.yml` |

### Verlauf

| PR | Inhalt |
|---|---|
| – | Erste Version direkt auf `main` |
| #1 | Abruf bei Berlin Recycling repariert (fehlender Zwischenschritt beim Login), vergangene Papiertermine behalten, lokaler Server liest `.env` |
| #2 | Kopfzeile neu gestaltet; `Cache-Control: no-cache`, damit Browser nach Updates keine alten CSS/JS-Dateien verwenden |
| #3 | Info-Kasten für Abholtage |
| #5 | Druckansicht als Jahresplaner auf einer A4-Seite quer (zum Eintragen), Berliner Feiertage, Skyline als Fußzeile |
| #6 | Benutzernummer für den Container per `.env` (`PUID`/`PGID`), damit die App auf der Synology in `data/` schreiben darf |
| #8 | Drucken auf dem iPhone: Kalender passt wieder auf eine Seite (vorher 2 Seiten im Querformat) |
| #7 | Erster Einsatz auf der Synology: README-Anleitung mit Deploy-Key, `$$` im Passwort, Hinweise zum Container Manager |
| – | Neues Design („Variante A“): App-Icon, Hero-Karte mit Countdown, Symbole je Müllart, farbig gefüllte Abholtage, Schatten statt Rahmen. Druckansicht unverändert |

## Offene Punkte

In etwa nach Wichtigkeit:

1. **Zweite Person als Mitarbeiterin einladen.** Sie hat noch keinen GitHub-Account. Sobald es einen gibt: auf GitHub unter Settings → Collaborators einladen (oder `gh api -X PUT repos/<owner>/abfuhrkalender-berlin/collaborators/<benutzername>`). Ab dann gilt: vor jedem Merge fragen (siehe „Arbeitsweise“).
2. **Nicht geprüft:**
   - Feiertagsberechnung (`berlinHolidays`, Ostern per Gauß-Formel) hat keine automatischen Tests – es gibt bisher keine JS-Tests. Für 2026 von Hand geprüft.
   - Druckvorschau in Safari/Firefox am Mac (geprüft: Chrome mit Rand 0 bis 20 mm und Safari auf dem iPhone, Quer- und Hochformat: je 1 Seite). Ob ein Browser trotzdem Kopf-/Fußzeilen (Datum, URL) druckt, hängt von seinen Druckeinstellungen ab.
   - Info-Kasten auf einem echten Handy (nur simuliertes Antippen getestet).
   - Neues Design nur in Chrome und im simulierten Handyfenster angesehen, nicht in Safari/Firefox und nicht auf einem echten Handy. `color-mix()` braucht Safari ab 16.2.
   - App-Icon als Favicon: Safari zeigt SVG-Favicons teils nicht oder ohne Hell/Dunkel-Wechsel.
   - Ob die App nach einem Neustart der Synology von selbst wieder startet (`restart: unless-stopped` ist gesetzt, aber noch nicht ausprobiert).
   - Live-Verhalten von `keep_past` – sichtbar erst, wenn Papiertermine in der Vergangenheit liegen (ab 01.12.2026); in Tests abgedeckt.
3. **Kleinigkeiten:**
   - GitHub Actions warnt, dass `actions/checkout@v4` und `actions/setup-python@v5` noch auf Node.js 20 laufen – bei Gelegenheit auf neuere Versionen heben.
   - `HEAD /` liefert 405 (nur `GET` ist definiert). Stört nicht, manche Monitoring-Tools prüfen aber per HEAD.
   - pytest zeigt eine Deprecation-Warnung aus Starlette (nicht unser Code).
4. **Für die spätere PWA:** Aus `app/static/icon.svg` PNG-Größen erzeugen (180 px für iPhone, 192/512 px, Fassung „maskable“ mit mehr Rand) und für 16/32 px eine vereinfachte Fassung zeichnen – das volle Motiv wird dort zum Klecks.
5. **Ideen, nicht beauftragt:** Fertiges Docker-Image per GitHub Actions bauen (GHCR), damit die Synology nicht selbst bauen muss; Erinnerung per Push/Mail.

## Lokale Umgebung

- Projektordner: `~/Documents/Claude/Projekte/muell-abfuhrkalender-berlin` (wurde einmal umgezogen; alte Pfade in älteren Sessions sind veraltet).
- `.venv/` – Python 3.12 via `uv`. Nach einem Umzug des Ordners funktioniert sie nicht mehr → löschen und neu anlegen (Befehle in CLAUDE.md).
- `.env` – existiert lokal mit echten Zugangsdaten fürs Kundenportal. **Nicht lesen, nicht ausgeben, nicht committen.** Zum Prüfen höchstens, *ob* die Werte gesetzt sind.
- `data/` – lokale Einstellungen und abgerufene Termine (enthält die echte Adresse, daher nicht im Repo).
- Server starten: `.venv/bin/uvicorn app.main:app --reload --port 8080 --env-file .env`, oder über `.claude/launch.json` (Name `abfuhrkalender`).

## Arbeitsweise

- Branch → Commit → Push → Pull Request → Tests auf GitHub abwarten → Merge (`gh pr merge --merge --delete-branch`) → lokal `main` aktualisieren.
- **Solange nur eine Person am Repo arbeitet**, darf Claude eigene PRs nach grünen Tests selbst mergen, wenn darum gebeten wird. **Sobald eine zweite Person mitarbeitet, vor jedem Merge fragen.**
- Pushen nur auf ausdrücklichen Wunsch.
- Commit-Nachrichten auf Deutsch, Imperativ, mit `Co-Authored-By`-Zeile, wenn Claude beteiligt war.
- Bei Änderungen an der Oberfläche: im Browser ansehen (hell, dunkel, Handybreite) und im PR schreiben, was nicht geprüft wurde.

## Stolpersteine (schon einmal passiert)

- **`$` im Passwort (Docker):** Docker liest die `.env` anders als der lokale Server und hält `$` für einen Platzhalter – das Passwort kam auf dem NAS gekürzt an, Login scheiterte. Lösung: in der `.env` auf dem NAS `$$` schreiben. Prüfen ohne die Werte zu zeigen: Länge per `docker exec` ausgeben (Befehl im README).
- **`.env` auf dem NAS geändert:** Container muss neu erstellt werden (`sudo docker compose up -d --force-recreate`), ein Neustart reicht nicht.
- **GitHub-Token ließ sich nicht anlegen** (Button „Generate token“ ohne Reaktion, in zwei Browsern). Deshalb holt das NAS den Code per Deploy-Key (nur Lesen, nur dieses Repo).
- **Container Manager meldet beim ersten Erstellen einen Fehler**, der Build lief aber im Hintergrund weiter und die App lief danach. Erst abwarten, dann per SSH `sudo docker compose build` für die echte Meldung.
- **Berlin-Recycling-Login:** Nach `Login.aspx/Auth` muss `Default.aspx` einmal per GET geöffnet werden, sonst antworten die Datenabfragen mit `{"Error": …}`. Der Test-Mock in `tests/conftest.py` bildet das über ein Sitzungs-Cookie nach.
- **Portal-Felder:** `Task Date` (Datum), `Material Description` (z. B. „Altpapier, gemischt“), `Description` ist die Behältergröße. Das Portal liefert nur die nächsten ~10 Termine.
- **BSR blockt Browser-Aufrufe** (`Origin`-Header → 403). Alles läuft über den Server.
- **`.env`-Änderungen** wirken erst nach einem Neustart des Servers (`--reload` lädt nur Code neu).
- **Browser-Cache:** Ohne `Cache-Control` hat ein Browser neue HTML-Seite mit alten CSS/JS kombiniert – sah völlig kaputt aus. Ist behoben (Middleware in `app/main.py`); bei Problemen nach einem Update trotzdem zuerst mit Cmd+Shift+R neu laden.
- **Tests und echte Webcalls:** `refresh.run()` ohne `client=` erzeugt einen echten HTTP-Client. In Tests immer den Mock-Client aus `conftest.py` übergeben.
- **Antippen auf dem Handy:** Ein Tipp löst erst `focusin`, dann `click` aus. Ob der Kasten schon offen war, wird deshalb bei `pointerdown` gemerkt (`initTooltip`).
- **Drucken auf dem iPhone ergab 2 Seiten:** iOS ignoriert `@page { margin: 0 }`, druckt mit eigenem Rand (gemessen ca. 17 mm rundherum) samt Datum/URL. Die feste Größe 297 × 209 mm passte nicht mehr, die Fußzeile rutschte auf Seite 2. Deshalb hat der `body` beim Drucken keine feste Größe mehr, sondern volle Breite und ein Seitenverhältnis (`aspect-ratio: 297 / 190`). Mit 297 / 198 passte zwar alles auf Seite 1, Safari hängte aber trotzdem eine leere zweite Seite an – es braucht etwas Luft. Hochformat war nie betroffen. Nachstellen: in `app.css` vorübergehend `margin: 12.7mm` bei `@page` setzen und mit Chrome drucken.
- **Druckansicht prüfen** geht am schnellsten mit Chrome ohne Fenster: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --no-pdf-header-footer --virtual-time-budget=4000 --print-to-pdf=druck.pdf http://localhost:8080/` – das PDF enthält die echte Adresse, also nicht ins Repo legen.
- **Browser-Testwerkzeug** klickt auch in der Handyansicht mit der Maus. Touch-Verhalten per `PointerEvent` mit `pointerType: "touch"` im Browser nachstellen.
