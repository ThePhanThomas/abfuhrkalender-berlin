# Projektstand und Übergabe

Diese Datei ist für alle – Menschen wie Claude –, die hier in einer neuen Session weiterarbeiten. Sie ergänzt die [CLAUDE.md](../CLAUDE.md) (Regeln und Konventionen) und das [README](../README.md) (Installation und Betrieb) um den **aktuellen Stand**: Was ist fertig, was ist offen, worüber ist man schon gestolpert.

**Bitte aktuell halten:** Wer ein Feature abschließt oder etwas Neues herausfindet, passt diese Datei im selben Pull Request an.

_Stand: 24.11.2026_

---

## Kurz gesagt

Die App läuft im Heimnetz auf der Synology (DS723+, Container Manager) und lokal zum Entwickeln. Alle vier Müllarten kommen automatisch:

| Müllart | Quelle | Status |
|---|---|---|
| Hausmüll, Biogut | BSR-API | ✅ funktioniert, inkl. Feiertagsverschiebungen |
| Wertstoffe (gelbe Tonne) | BSR-API (Abfuhr durch ALBA) | ✅ funktioniert |
| Papier | Berlin Recycling Kundenportal (Login) | ✅ funktioniert mit echtem Login getestet |

Läuft seit 22.11.2026 auf der Synology, alle vier Müllarten werden dort abgerufen. Seit 22.11.2026 auch als App auf dem iPhone, Push-Erinnerung funktioniert. Seit 23.11.2026 läuft HTTPS über eine eigene Domain mit Let's-Encrypt-Zertifikat statt über Tailscale (siehe „Betrieb auf dem NAS“).

## Was fertig ist

| Funktion | Wo im Code |
|---|---|
| Einrichtung der Adresse in der App (Suche über BSR, keine Adresse im Code) | `app/static/app.js` (Einstellungen), `app/sources/bsr.py` |
| Einstellungen als Karten (Adresse, Müllarten, Papier, Erinnerung), unten feste Leiste „Abbrechen / Speichern“, auf dem Handy als Blatt von unten. Adresse klappt erst bei „Ändern“ auf, Vorschläge beim Tippen (`scheduleSearch`, 450 ms Pause). Müllarten als Kacheln; Papier-Einstellung nur, wenn die Kachel „Papier“ an ist (aus = `paper.mode: "off"`). Push als Schalter. Alle Dialoge fahren von unten ins Bild und beim Schließen wieder hinaus (auf dem Handy als Blatt vom unteren Rand); geschlossen wird darum über `closeDialog`, nicht direkt mit `.close()` | `index.html` (`#dlg-settings`), `app.js` (`openSettings`, `updatePaper`, `searchAddress`), `app.css` |
| Jahresübersicht (jeder Monat mit sechs Wochenzeilen, damit alle Karten gleich hoch sind): Abholtage farbig gefüllt (zwei Arten = diagonal geteilt, drei oder mehr = gleich große Tortenstücke), laufender Monat hervorgehoben, vergangene Monate blasser, Feiertagsverschiebung als roter Punkt. Im laufenden Jahr liegen vergangene Monate als Stapel hinter dem laufenden Monat (oben „Januar – Oktober ˄“, darunter zwei Kanten, die oben hinter der Karte hervorschauen; Karten unten bündig, `align-items: end`), nach jedem Laden wieder; Aufklappen teilt die Karten aus dem Stapel aus, „einklappen“ schiebt sie wieder darunter, danach gleiten die Kanten oben hinter dem Monat hervor (Kopien `.month-ghost`, bei „Bewegung reduzieren“ ohne Animation); Druck zeigt immer das ganze Jahr | `app/static/app.js` (`renderMonths`, `setEarlier`) |
| „Nächste Abholung“ als große Karte mit Countdown („in / 2 / Tagen“ gestapelt, sonst „Heute“/„Morgen“), übrige Müllarten als Liste daneben mit Farbstreifen der Müllart am linken Rand. Gibt es heute **und** morgen Abholungen, heißt die Karte „Heute und morgen“ und hat eine Zeile pro Tag (gleiche Tage zusammen, bei morgen der Hinweis „Heute Abend rausstellen“); Symbol je Müllart (`CAT_ICONS`) | `app/static/app.js` (`renderNext`, `tile`) |
| Tonne als „rausgestellt“ bzw. „abgeholt“ markieren: runder Knopf in der großen Karte ab dem Vorabend (am Vorabend an/aus, am Abholtag nichts → draußen → abgeholt → nichts; mehrere Tonnen eines Tages teilen sich einen Knopf). Haken zeichnet sich in der Farbe der Müllart, Kachel rollt ein Stück zur Seite, nach der Abholung wird sie blasser (bei „Bewegung reduzieren“ ohne Animation). Gespeichert auf dem Server in `data/marks.json`, damit alle Geräte dasselbe sehen; vergangene Tage fliegen bei jedem Lesen/Schreiben heraus, markieren geht nur von heute bis 7 Tage voraus. Schon rausgestellte Tonnen fallen aus der Abend-Erinnerung. Ohne Server springt die Markierung zurück, Hinweis im Banner | `app/static/app.js` (`markButton`, `toggleMark`), `app.css` (`.mark`), `app/store.py` (`load_marks`, `set_mark`), `app/main.py` (`PUT /api/marks`), `app/push.py` (`reminder_for`) |
| App-Icon (Tonne, Kalenderblatt, Fernsehturm): hell in BSR-Orange, dunkel in Nachtblau, jeweils mit feinem Verlauf. `icon.svg` (Favicon, Vorlage für die PNGs) folgt dem System; die Kopfzeile zeigt dieselbe Grafik inline, damit sie dem gewählten Design folgt – Änderungen an beiden Stellen machen | `app/static/icon.svg`, `index.html` (`.appicon`), PNGs per `tools/make_icons.py` |
| Akzentfarbe BSR-Orange (`--accent` für Schrift, `--accent-strong` für Ringe/Rahmen): „Aktualisieren“, heutiger Tag als Ring, Rahmen um den laufenden Monat | `app/static/app.css` |
| Design hell/dunkel/automatisch per Knopf in der Kopfzeile, pro Gerät gespeichert (`localStorage` „theme“). Ein kleines Skript im `<head>` setzt `data-theme` vor dem ersten Zeichnen; das dunkle Design gilt nur am Bildschirm (`@media screen`), der Ausdruck bleibt hell. Beim Umschalten breitet sich das neue Design als Kreis vom Knopf aus (View Transitions; ältere Browser und „Bewegung reduzieren“ schalten sofort um) | `index.html`, `app.js` (`applyTheme`, `cycleTheme`), `app.css` |
| Filter: Die Müllarten über dem Kalender sind Knöpfe; Antippen blendet eine Müllart in „Nächste Abholung“, Kalender und Ausdruck aus (gestrichelt, grau) bzw. wieder ein. Mindestens eine bleibt sichtbar. Die Karten bei „Nächste Abholung“ behalten dabei ihre Größe (`renderNext` misst sie erst ungefiltert; leere Liste zeigt „Weitere Müllarten ausgeblendet“). Pro Gerät gespeichert (`localStorage` „hidden-cats“), unabhängig von den Müllarten in den Einstellungen | `app/static/app.js` (`hiddenCats`, `toggleCat`, `renderLegend`, `renderNext`/`fillNext`), `app.css` (`button.chip`) |
| Info-Kasten pro Abholtag (Maus, Antippen, Tastatur) | `app/static/app.js` (`initTooltip`, `showTip`) |
| Kopfzeile mit App-Icon, Überschrift „Abfuhrkalender **Berlin**“ („Berlin“ in BSR-Orange, nur am Bildschirm) und Jahres-Umschalter „‹ 2026 ›“, bleibt beim Scrollen oben (durchscheinend), oben um den Systemrand eingerückt (`viewport-fit=cover`, `env(safe-area-inset-*)`); in der iPad-App 28 px tiefer (Klasse `ipad-app`, `--ipad-top-gap`) | `app/static/index.html`, `app.css` |
| Button „Aktualisieren“ + automatischer Abruf (Standard wöchentlich) | `app/main.py` (`_auto_refresh_loop`), `app/refresh.py` |
| Papier: Kundenportal **oder** selbst angegebener Turnus **oder** aus | `app/sources/berlin_recycling.py`, `app/sources/manual.py` |
| Vergangene Papiertermine bleiben erhalten (Portal liefert nur kommende) | `app/refresh.py` (`keep_past`) |
| Kalender-Abo (`/api/calendar.ics`), optional Erinnerung am Vorabend 18 Uhr | `app/ics.py` |
| Druckansicht als Jahresplaner auf **einer** A4-Seite quer: je Monat eine Spalte mit Platz zum Eintragen, Wochenenden schattiert, Berliner Feiertage, KW, Fußzeile mit Berliner Skyline | `app/static/app.js` (`renderPlanner`, `berlinHolidays`), `app.css` (`@media print`), Fußzeile in `index.html` |
| Helles/dunkles Design, Handy-Layout | `app/static/app.css` |
| PWA: Symbol auf dem Home-Bildschirm (Manifest, PNG-Icons), Service Worker zeigt ohne Server den letzten Stand mit orangem Hinweis „Stand vom …“ | `app/static/sw.js`, `manifest.webmanifest`, `icons/`, `app.js` (`loadState`), Icons per `tools/make_icons.py` |
| Push-Erinnerung am Vorabend (Uhrzeit einstellbar, Standard 18 Uhr; pro Gerät ein-/ausschaltbar, „Test senden“). Schlüssel in `data/vapid.json`, Geräte in `data/push.json` | `app/push.py`, `app/main.py` (`/api/push/*`, `_push_loop`), `app.js` (`renderPush`, `togglePush`) |
| Push-Hinweise (08–21 Uhr): Vorwarnung ca. 7 Tage vor einem verschobenen Termin (`moved_from`), „Termin geändert“ bei Abweichungen zwischen zwei Abrufen (nächste 14 Tage, nur BSR bei gleicher Adresse und Berlin Recycling), Meldung ab dem 2. Fehlschlag einer Quelle und „klappt wieder“. Nach einem Fehlschlag neuer Abruf nach 6 h. Abend-Erinnerung nennt Verschiebung. Fehlerbanner zeigt „(seit TT.MM.)“. Gemerkt in `push.json` (`failure_alerted`, `moved_announced`, `changes_sent`), Änderungen in `pickups.json` (`changes`) | `app/push.py` (`run_alerts`, `_collect_alerts`), `app/refresh.py` (`detect_changes`, `fail_count`/`failed_since`), `app/main.py` (`_refresh_due`) |
| Docker-Setup für jeden Rechner mit Docker (im Einsatz auf einer Synology DS723+), Benutzernummer per `PUID`/`PGID`; README erklärt erst den allgemeinen Weg, dann die Synology als Beispiel | `Dockerfile`, `docker-compose.yml`, README |
| Tests (56, alle Webcalls gemockt, Push-Versand gesperrt) + GitHub Actions bei Push/PR | `tests/`, `.github/workflows/tests.yml` |

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
| – | Bio kräftiger braun, Wertstoffe zitronengelb (waren schwer zu unterscheiden); Einstellungsdialog auf dem Handy: Eingabefelder 16 px, damit Safari nicht hineinzoomt, Felder untereinander |
| – | Glas und Sonstiges aus den Einstellungen entfernt (keine Quelle liefert dafür Termine); „Rhythmus“ heißt jetzt „Turnus“ |
| – | PWA: Home-Bildschirm-Symbol, Anzeige ohne Server, Push-Erinnerung am Vorabend; HTTPS über Tailscale (Anleitung im README). Neue Abhängigkeiten `pywebpush`, `tzdata` |
| – | Vergangene Monate des laufenden Jahres eingeklappt, per Zeile einblendbar |
| – | Drucken in der iPhone-App: Hinweis-Dialog mit „In Safari öffnen“, Safari druckt dann von selbst (`?print=<Jahr>`) |
| – | README und Repo-Beschreibung allgemeiner: Betrieb auf jedem Rechner mit Docker, Synology nur noch als Beispiel |
| – | Liste „Danach“: Farbstreifen der Müllart am linken Kartenrand, Trennlinien zwischen den Zeilen |
| – | Push-Hinweise bei verschobenen/geänderten Terminen und bei fehlschlagenden Abrufen |
| #20 | Neues App-Icon (BSR-Orange/Nachtblau), Akzentfarbe Orange statt Blau, Umschalter hell/dunkel/automatisch, Animation beim Ein-/Ausblenden vergangener Monate. Druckansicht unverändert |
| – | Countdown „in 2 Tagen“ statt „2 Tage“, Überschrift mit oranger „Berlin“. Druckansicht unverändert |
| – | Druck-Fußzeile: Skyline überarbeitet (Funkturm geschwungen, Brandenburger Tor schmaler mit Quadriga, Fernsehturm mit kleinerer Kugel, Endpfeiler an der Oberbaumbrücke). Feiertagsnamen im Druck kleiner (4,6 pt), 25./26.12. heißen „Weihnachten“, Heiligabend und Silvester beschriftet (ohne Feiertagsfarbe, `specialDays`), Safari darf kleine Schrift nicht mehr selbst vergrößern (`text-size-adjust`) |
| – | Einstellungen neu sortiert (Karten, Kacheln, Schalter, Vorschläge beim Tippen); vergangene Monate als Stapel unter dem laufenden Monat |
| #26 | iPad-App: Kopfzeile um den Systemrand eingerückt (half auf dem iPad nicht) |
| #27 | iPad-App: Kopf 28 px tiefer, unter die Unschärfe am oberen Rand; Glaseffekt bleibt (auf dem iPad geprüft) |
| – | Kacheln heben sich besser ab: Hintergrund etwas dunkler (hell `#f1efe9`, dunkel `#151514`), Schatten kräftiger mit feiner Kante; Farbe auch in `theme-color`/Manifest. Druckansicht unverändert |
| #31 | Vorbereitung fürs Öffentlichmachen: Repo, Historie und PRs auf persönliche Daten geprüft (nichts gefunden), MIT-Lizenz (`LICENSE`) und Hinweis „Kein offizielles Angebot“ im README; README: Code per `git clone https://…` statt Deploy-Key |
| – | Repo auf GitHub öffentlich geschaltet (22.11.2026) |
| – | HTTPS auf dem NAS über eigene Domain statt Tailscale; README beschreibt HTTPS jetzt allgemein (eigene Domain, Tailscale, vorhandener Reverse Proxy). Hinweise in der App sagen „per VPN“ statt „mit Tailscale“ |

## Offene Punkte

In etwa nach Wichtigkeit:

1. **Zweite Person als Mitarbeiterin einladen.** Sie hat noch keinen GitHub-Account. Sobald es einen gibt: auf GitHub unter Settings → Collaborators einladen (oder `gh api -X PUT repos/<owner>/abfuhrkalender-berlin/collaborators/<benutzername>`). Ab dann gilt: vor jedem Merge fragen (siehe „Arbeitsweise“).
2. **Nicht geprüft:**
   - Feiertagsberechnung (`berlinHolidays`, Ostern per Gauß-Formel) hat keine automatischen Tests – es gibt bisher keine JS-Tests. Für 2026 von Hand geprüft.
   - Druckvorschau in Safari/Firefox am Mac (geprüft: Chrome mit Rand 0 bis 20 mm und Safari auf dem iPhone, Quer- und Hochformat: je 1 Seite). Ob ein Browser trotzdem Kopf-/Fußzeilen (Datum, URL) druckt, hängt von seinen Druckeinstellungen ab.
   - Info-Kasten auf einem echten Handy (nur simuliertes Antippen getestet).
   - Neues Design nur in Chrome und im simulierten Handyfenster angesehen, nicht in Safari/Firefox und nicht auf einem echten Handy. `color-mix()` braucht Safari ab 16.2.
   - Neues Design, Hell/Dunkel-Umschalter und Monats-Animation nur in Chrome (auch Handybreite) geprüft, nicht in Safari und nicht auf dem echten iPhone. Das Home-Bildschirm-Icon aktualisiert iOS erst, wenn man die App vom Home-Bildschirm entfernt und neu hinzufügt.
   - App-Icon als Favicon: Safari zeigt SVG-Favicons teils nicht oder ohne Hell/Dunkel-Wechsel.
   - Betrieb außerhalb der Synology (anderes NAS, Raspberry Pi, Linux-Server) – die allgemeine Anleitung im README ist dort noch nicht ausprobiert.
   - Ob die App nach einem Neustart der Synology von selbst wieder startet (`restart: unless-stopped` ist gesetzt, aber noch nicht ausprobiert).
   - PWA: Auf dem echten iPhone geprüft sind Home-Bildschirm, Push-Anmeldung und „Test senden“ (Apple akzeptiert die Platzhalter-Absenderangabe). Noch nicht beobachtet: die echte Erinnerung am Vorabend und die Anzeige ohne Server auf dem iPhone (am Mac geprüft).
   - Push ohne VPN auf dem iPhone: Mit ausgeschaltetem Tailscale kam auf dem iPhone eine Mitteilung nicht an, auf dem iPad zu Hause schon. Laut Code braucht der Empfang keine Verbindung zum Server; vermutlich war es „Test senden“ (erreicht ohne Verbindung den Server nicht und gilt nur fürs eigene Gerät) oder die Anmeldung des iPhones war weg. Nach dem Umstieg auf die eigene Domain neu angemeldet – die nächste Abend-Erinnerung ohne VPN beobachten.
   - Erste automatische Erneuerung des Zertifikats (fällig etwa Ende Januar 2027) noch nicht beobachtet.
   - Feiertagsnamen im Druck: in Chrome geprüft (passen in die Zeile), noch nicht auf dem iPhone – dort ragte „Ostermontag“ aus der Zeile, vermutlich weil Safari kleine Schrift vergrößert hat.
   - Drucken aus der iPhone-App: Der Sprung nach Safari (`x-safari-https:`, ab iOS 17) ist nur am Mac nachgestellt, nicht auf dem echten iPhone. Der automatische Druck nach `?print=<Jahr>` ist in Chrome geprüft.
   - Push-Hinweise (Verschiebung, Termin geändert, Abruffehler) nur in Tests geprüft, noch nicht live beobachtet. Erste echte Feiertagsverschiebung: Weihnachten/Neujahr 2026/27 – die Verschiebungen auf den 21./22.12.2026 werden im Kalender richtig angezeigt (mit BSR-Seite verglichen). Das Fehlerbanner mit „(seit …)“ ist nicht im Browser angesehen.
   - Karte „Heute und morgen“ und dreigeteilte Kalendertage nur in Chrome (hell, dunkel, Handybreite) geprüft, gleiche Tage und drei Arten mit erfundenen Terminen im Browser nachgestellt.
   - Markieren (rausgestellt/abgeholt) nur in Chrome geprüft (hell, dunkel, Handybreite, ohne Server), nicht auf dem echten iPhone. Ob die Abend-Erinnerung bei markierter Tonne live ausbleibt, ist nur in Tests geprüft. Markierungen anderer Geräte erscheinen erst nach Neuladen oder Zurückkehren in die App.
   - Live-Verhalten von `keep_past` – sichtbar erst, wenn Papiertermine in der Vergangenheit liegen (ab 01.12.2026); in Tests abgedeckt.
3. **Kleinigkeiten:**
   - GitHub Actions warnt, dass `actions/checkout@v4` und `actions/setup-python@v5` noch auf Node.js 20 laufen – bei Gelegenheit auf neuere Versionen heben.
   - Wie viele Geräte eine Erinnerung erreicht hat, steht nirgends im Protokoll (`log.info` in `push.py` wird nicht ausgegeben), und Anmeldungen, die Apple als ungültig meldet, verschwinden still. Erschwert die Fehlersuche bei Push.
   - Auf dem NAS gibt es noch keine Umleitung von http auf https für die App (optional, Browser versuchen ohnehin zuerst https). Ginge mit einer kleinen nginx-Datei in `/usr/local/etc/nginx/sites-enabled/`, die ein DSM-Update aber entfernen kann.
   - `HEAD /` liefert 405 (nur `GET` ist definiert). Stört nicht, manche Monitoring-Tools prüfen aber per HEAD.
   - pytest zeigt eine Deprecation-Warnung aus Starlette (nicht unser Code).
   - Favicon: für 16/32 px eine vereinfachte Fassung des Icons zeichnen – das volle Motiv wird dort zum Klecks. (Die PWA-Icons 180/192/512 px gibt es.)
4. **Commit-Autoren:** Das Repo ist seit 22.11.2026 öffentlich. Ältere Commits nennen als Autor den vollen Namen und den Rechnernamen (`…@Mac.fritz.box`) – ob die Historie umgeschrieben wird, ist noch nicht entschieden (bräuchte ein erzwungenes Überschreiben auf GitHub und ein neues Holen auf dem NAS). Für neue Commits lässt sich die anonyme GitHub-Adresse einstellen (`git config user.email "<id>+<name>@users.noreply.github.com"`).
5. **Ideen, nicht beauftragt:** Fertiges Docker-Image per GitHub Actions bauen (GHCR), damit die Synology nicht selbst bauen muss; Erinnerung per Mail.

## Betrieb auf dem NAS (HTTPS)

Ohne Namen und Domain, die stehen nur auf dem NAS bzw. beim Domain-Anbieter:

- Ein Name unter unserer Domain (plus `*.` davor für alles darunter) zeigt per A-Eintrag auf die feste Heimnetz-Adresse des NAS. Die App läuft unter einem Namen darunter.
- Zertifikat (Let's Encrypt, Wildcard) per **acme.sh** direkt auf dem NAS, installiert in `/usr/local/share/.acme.sh`, DNS-Prüfung über die Schnittstelle des Domain-Anbieters (Modul `dns_kas`). Die Zugangsdaten dafür liegen nur dort in `account.conf` (nur root).
- Eingespielt in DSM per `--deploy-hook synology_dsm` mit `SYNO_USE_TEMP_ADMIN=1` (kein DSM-Passwort gespeichert). Erneuerung wöchentlich über den DSM-Aufgabenplaner als root: `acme.sh --cron --home /usr/local/share/.acme.sh`.
- DSM-Reverse-Proxy: HTTPS 443 → `localhost:8080`. Kein HSTS (bewusst, damit ein Zertifikatsproblem die App nicht sperrt).
- Tailscale ist vom NAS und von den Geräten entfernt; von unterwegs geht es per WireGuard ins Heimnetz.
- Sobald Let's Encrypt **DNS-PERSIST-01** anbietet (Stand Nov. 2026 noch nicht), kann die Prüfung auf einen festen DNS-Eintrag umgestellt werden; dann müssen die Zugangsdaten des Domain-Anbieters nicht mehr auf dem NAS liegen.

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
- **GitHub-Token ließ sich nicht anlegen** (Button „Generate token“ ohne Reaktion, in zwei Browsern). Deshalb holt unser NAS den Code per Deploy-Key (nur Lesen, nur dieses Repo, Adresse `github-abfuhrkalender:…`). Das funktioniert auch nach dem Öffentlichmachen weiter; im README steht jetzt nur noch der einfache Weg per `git clone https://…`.
- **Container Manager meldet beim ersten Erstellen einen Fehler**, der Build lief aber im Hintergrund weiter und die App lief danach. Erst abwarten, dann per SSH `sudo docker compose build` für die echte Meldung.
- **Berlin-Recycling-Login:** Nach `Login.aspx/Auth` muss `Default.aspx` einmal per GET geöffnet werden, sonst antworten die Datenabfragen mit `{"Error": …}`. Der Test-Mock in `tests/conftest.py` bildet das über ein Sitzungs-Cookie nach.
- **Müllarten ohne Termine:** Laubtonne und Weihnachtsbaum kommen von der BSR, aber nur, wenn es sie an der Adresse gibt (Weihnachtsbaum nur im Januar, also oft erst im nächsten Jahr sichtbar). Glas und Sonstiges sind nicht wählbar: Das Kundenportal würde Glas zwar als `GL` erkennen, liefert bei uns aber nur Papier. Ältere `config.json` mit `GL`/`SO` werden beim Laden bereinigt (`store.load_config`).
- **Portal-Felder:** `Task Date` (Datum), `Material Description` (z. B. „Altpapier, gemischt“), `Description` ist die Behältergröße. Das Portal liefert nur die nächsten ~10 Termine.
- **BSR blockt Browser-Aufrufe** (`Origin`-Header → 403). Alles läuft über den Server.
- **`.env`-Änderungen** wirken erst nach einem Neustart des Servers (`--reload` lädt nur Code neu).
- **Browser-Cache:** Ohne `Cache-Control` hat ein Browser neue HTML-Seite mit alten CSS/JS kombiniert – sah völlig kaputt aus. Ist behoben (Middleware in `app/main.py`); bei Problemen nach einem Update trotzdem zuerst mit Cmd+Shift+R neu laden.
- **Tests und echte Webcalls:** `refresh.run()` ohne `client=` erzeugt einen echten HTTP-Client. In Tests immer den Mock-Client aus `conftest.py` übergeben.
- **Antippen auf dem Handy:** Ein Tipp löst erst `focusin`, dann `click` aus. Ob der Kasten schon offen war, wird deshalb bei `pointerdown` gemerkt (`initTooltip`).
- **Drucken auf dem iPhone ergab 2 Seiten:** iOS ignoriert `@page { margin: 0 }`, druckt mit eigenem Rand (gemessen ca. 17 mm rundherum) samt Datum/URL. Die feste Größe 297 × 209 mm passte nicht mehr, die Fußzeile rutschte auf Seite 2. Deshalb hat der `body` beim Drucken keine feste Größe mehr, sondern volle Breite und ein Seitenverhältnis (`aspect-ratio: 297 / 190`). Mit 297 / 198 passte zwar alles auf Seite 1, Safari hängte aber trotzdem eine leere zweite Seite an – es braucht etwas Luft. Hochformat war nie betroffen. Nachstellen: in `app.css` vorübergehend `margin: 12.7mm` bei `@page` setzen und mit Chrome drucken.
- **Einstellungen auf dem iPhone zu breit:** Eingabefelder hatten 13 px Schrift; Safari zoomt bei unter 16 px beim Antippen hinein, danach musste man seitlich scrollen. In der Simulation am Mac nicht nachstellbar, weil dort nicht gezoomt wird – auf einem echten iPhone prüfen.
- **Druckansicht prüfen** geht am schnellsten mit Chrome ohne Fenster: `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --no-pdf-header-footer --virtual-time-budget=4000 --print-to-pdf=druck.pdf http://localhost:8080/` – das PDF enthält die echte Adresse, also nicht ins Repo legen.
- **Tailscale-HTTPS lud endlos** (erste Einrichtung, inzwischen nicht mehr in Gebrauch): `tailscale serve --bg 8080` lief, `https://…ts.net` hing. Nach einmaligem `tailscale cert <name>.ts.net` auf dem NAS ging es sofort. Der Befehlspfad auf der Synology ist `/var/packages/Tailscale/target/bin/tailscale`.
- **Fritz!Box blockiert den eigenen Namen:** Öffentlicher Name mit Heimnetz-Adresse → leere DNS-Antwort (DNS-Rebind-Schutz). Ausnahme unter Heimnetz → Netzwerk → Netzwerkeinstellungen eintragen; Namen darunter sind mit abgedeckt. Prüfen mit `dig +short @<Router-IP> <name>`.
- **acme.sh auf der Synology:** In `/tmp` dürfen keine Programme gestartet werden („Permission denied“) – zum Installieren `sh ./acme.sh --install …`. Ohne `--server letsencrypt` nimmt acme.sh ZeroSSL.
- **DSM nutzte trotz „Standardzertifikat“ weiter das alte:** In Sicherheit → Zertifikat → Einstellungen muss bei **Systemstandard** das neue Zertifikat ausgewählt sein; „Standardzertifikat“ gilt nur für Dienste ohne eigene Zuordnung.
- **Zwei-Faktor-Pflicht beim Einspielen:** Mit `SYNO_USE_TEMP_ADMIN=1` setzt acme.sh die 2FA-Pflicht für Admins bei jeder Erneuerung für ein paar Sekunden aus und stellt sie wieder her (steht in der Ausgabe). Bei Problemen in Systemsteuerung → Sicherheit → Konto nachsehen.
- **Service Worker und Push brauchen HTTPS** (Ausnahme: `localhost`). Über `http://<NAS-IP>:8080` meldet sich kein Service Worker an, die App läuft dann wie vorher. Auf dem iPhone geht Push außerdem nur, wenn die App vom Home-Bildschirm geöffnet wird, nicht in Safari.
- **Offline testen:** Seite einmal laden (Service Worker speichert Seite und `/api/state`), Server stoppen, neu laden → blauer Hinweis mit Stand. Der Service Worker holt immer zuerst frisch vom Server (5 s Wartezeit), deshalb muss die Cache-Version (`CACHE` in `sw.js`) bei Updates nicht erhöht werden.
- **Verschiebung erkennen:** Die BSR meldet Feiertagsverschiebungen als neuen Termin mit `moved_from`; der alte Termin fällt dabei aus der Liste. `detect_changes` überspringt solche Termine, sonst käme fälschlich „entfällt“. Berlin Recycling kennt kein `moved_from`, dort hilft nur der Vergleich zweier Abrufe.
- **`data/vapid.json` nicht löschen:** Das ist der Push-Schlüssel des Servers. Ein neuer Schlüssel macht alle Anmeldungen ungültig; jedes Gerät muss Push dann neu einschalten.
- **Drucken in der iPhone-App geht nicht:** iOS ignoriert `window.print()` in Apps vom Home-Bildschirm stillschweigend. Deshalb zeigt der Drucken-Button dort einen Dialog, der die Seite per `x-safari-https://…/?print=<Jahr>` in Safari öffnet; Safari wählt das Jahr, entfernt den Parameter aus der Adresse und öffnet den Druckdialog (`printPlanner`, Ende von `init` in `app.js`).
- **Animationen mit Vorher/Nachher-Messung (FLIP):** `getBoundingClientRect()` enthält laufende Transformationen. Zielpunkte deshalb messen, bevor ein Element animiert wird – sonst flogen die Monate beim Einklappen zur alten Stelle des laufenden Monats. Zum Prüfen Animationen anhalten: `document.getAnimations().forEach(a => { a.pause(); a.currentTime = 250; })`.
- **Browser-Testwerkzeug** klickt auch in der Handyansicht mit der Maus. Touch-Verhalten per `PointerEvent` mit `pointerType: "touch"` im Browser nachstellen.
- **Unscharfe Schrift oben in der iPad-App:** iPadOS legt im Fenstermodus über Uhrzeit und Fensterknöpfe eine Unschärfe, meldet der Seite dafür aber keinen Rand (`env(safe-area-inset-top)` ist 0, das Einrücken darum half nicht). Deshalb erkennt ein Skript im `<head>` die iPad-App (iPad gibt sich als Mac mit Touchscreen aus, dazu `navigator.standalone`) und setzt die Klasse `ipad-app`; der Kopf rückt dann um `--ipad-top-gap` nach unten.
