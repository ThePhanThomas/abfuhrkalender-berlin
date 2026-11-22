"use strict";

const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const WEEKDAYS_LONG = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
const SOURCE_NAMES = { bsr: "BSR", berlin_recycling: "Berlin Recycling", paper_manual: "Papier (manuell)" };

// Line icons per waste type (24 × 24, stroke = currentColor)
const CAT_ICONS = {
  HM: '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2l1-12M9 7V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3"/>',
  BI: '<path d="M5 19c0-8 5-13 15-14-1 10-6 15-14 15"/><path d="M5 19c3-4 6-7 10-9"/>',
  WS: '<path d="M10 3h4v3l2 3v11a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V9l2-3z"/><path d="M8 13h8"/>',
  PP: '<path d="M5 4h11l3 3v13H5z"/><path d="M8 9h8M8 13h8M8 17h5"/>',
  LT: '<path d="M12 21v-8M12 13c-5 0-8-3-8-8 5 0 8 3 8 8zM12 13c5 0 8-3 8-8-5 0-8 3-8 8z"/>',
  WB: '<path d="M12 3l5 7h-3l4 6H6l4-6H7zM12 16v5"/>',
  SO: '<circle cx="12" cy="12" r="3"/><path d="M12 4v2M12 18v2M4 12h2M18 12h2"/>',
};
const catIcon = (c) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${CAT_ICONS[c] || CAT_ICONS.SO}</svg>`;
const tile = (c) => `<span class="tile" style="--c: var(--c-${c})">${catIcon(c)}</span>`;

const $ = (id) => document.getElementById(id);
let state = null;
let selectedYear = null;
let pendingAddress = null;
let availableYears = [];
let showEarlier = false; // vergangene Monate des laufenden Jahres eingeblendet? Wird bewusst nicht gespeichert.
let offlineSince = null; // null = Server erreichbar; sonst ISO-Zeit des gezeigten Stands ("" = unbekannt)

// ---------- helpers ----------
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseIso = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const fmtLong = (s) => { const d = parseIso(s); return `${WEEKDAYS_LONG[d.getDay()]}, ${d.getDate()}. ${MONTHS[d.getMonth()]}`; };
const fmtDate = (s) => { const d = parseIso(s); return `${WEEKDAYS[d.getDay()]}, ${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`; };
const catName = (c) => (state && state.categories[c]) || c;
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

const OFFLINE_MSG = "Keine Verbindung zum Server. Das geht nur im Heimnetz (oder mit Tailscale).";

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  } catch {
    throw new Error(OFFLINE_MSG);
  }
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d) => d.msg).join(", ");
    } catch { /* keep default */ }
    throw new Error(msg);
  }
  return res.json();
}

// Lädt den Stand vom Server. Ist der nicht erreichbar, liefert der Service
// Worker den zuletzt gespeicherten Stand und markiert ihn mit "X-Offline".
async function loadState() {
  let res;
  try {
    res = await fetch("/api/state", { headers: { Accept: "application/json" } });
  } catch {
    throw new Error(OFFLINE_MSG);
  }
  if (!res.ok) throw new Error(`Fehler ${res.status}`);
  offlineSince = res.headers.get("X-Offline") ? res.headers.get("X-Cached-At") || "" : null;
  state = await res.json();
}

const fmtStamp = (isoString) => {
  const d = new Date(isoString);
  return `${d.toLocaleDateString("de-DE")}, ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })} Uhr`;
};

function visiblePickups() {
  const cats = new Set(state.config.categories);
  return state.pickups.filter((p) => cats.has(p.category));
}

// ---------- rendering ----------
function render() {
  const cfg = state.config;
  $("address-label").textContent = cfg.address ? cfg.address.label : "Adresse einrichten";
  renderStatus();
  renderYears();
  renderNext();
  renderLegend();
  renderMonths();
}

function failedSuffix(s) {
  if (!s.failed_since) return "";
  const since = new Date(s.failed_since);
  if (Date.now() - since.getTime() <= 24 * 3600 * 1000) return "";
  return ` (seit ${since.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })})`;
}

function renderStatus() {
  const parts = [];
  if (state.updated_at) {
    const d = new Date(state.updated_at);
    parts.push(`Zuletzt aktualisiert: ${d.toLocaleDateString("de-DE")}, ${d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}`);
  } else {
    parts.push("Noch keine Daten abgerufen");
  }
  const errors = [];
  for (const [name, s] of Object.entries(state.sources)) {
    const label = SOURCE_NAMES[name] || name;
    if (s.ok) parts.push(`${esc(label)} ok (${s.count} Termine)`);
    else { parts.push(`<span class="bad">${esc(label)}: Fehler</span>`); errors.push(`${label}: ${s.error}${failedSuffix(s)}`); }
  }
  $("status").innerHTML = parts.map((p, i) => (i === 0 ? esc(p) : p)).join(" · ");
  const banner = $("banner");
  banner.classList.toggle("offline", offlineSince !== null);
  if (offlineSince !== null) {
    banner.hidden = false;
    banner.textContent = `Keine Verbindung zum Server – du siehst den gespeicherten Stand${offlineSince ? ` vom ${fmtStamp(offlineSince)}` : ""}. Aktualisieren und Einstellungen gehen nur im Heimnetz (oder mit Tailscale).`;
    return;
  }
  banner.hidden = errors.length === 0;
  banner.textContent = errors.length ? `${errors.join(" · ")} — vorhandene Termine bleiben erhalten.` : "";
}

function renderYears() {
  const years = new Set([new Date().getFullYear()]);
  state.pickups.forEach((p) => years.add(Number(p.date.slice(0, 4))));
  const sorted = [...years].sort();
  if (!selectedYear || !years.has(selectedYear)) selectedYear = new Date().getFullYear();
  availableYears = sorted;
  $("year").textContent = selectedYear;
  $("print-year").textContent = selectedYear;
  $("print-date").textContent = fmtDate(iso(new Date())).slice(4);
  $("year-prev").disabled = selectedYear <= sorted[0];
  $("year-next").disabled = selectedYear >= sorted[sorted.length - 1];
  document.title = `Abfuhrkalender ${selectedYear}`;
}

function renderNext() {
  const today = iso(new Date());
  const next = new Map();
  for (const p of visiblePickups()) {
    if (p.date >= today && !next.has(p.category)) next.set(p.category, p);
  }
  const items = [...next.values()].sort((a, b) => a.date.localeCompare(b.date));
  if (!items.length) {
    $("next").innerHTML = `<p class="empty">${state.config.address ? "Keine kommenden Termine. Daten aktualisieren?" : "Richte zuerst deine Adresse ein."}</p>`;
    return;
  }
  const daysUntil = (p) => Math.round((parseIso(p.date) - parseIso(today)) / 864e5);
  const moved = (p) => (p.moved_from ? ` · <span class="moved-note">verschoben</span>` : "");
  // All pickups on the first upcoming date share the hero card (e.g. Bio and Hausmüll on the same day).
  const first = items.filter((p) => p.date === items[0].date);
  const rest = items.filter((p) => p.date !== items[0].date);
  const n = daysUntil(first[0]);
  const count = n === 0 ? `<b>Heute</b>` : n === 1 ? `<b>Morgen</b>` : `<b>${n}</b><span>Tage</span>`;
  const hero = `<div class="hero-main${n <= 1 ? " soon" : ""}" style="--c: var(--c-${first[0].category})">
      <div class="hero-tiles">${first.map((p) => tile(p.category)).join("")}</div>
      <div class="hero-text">
        <div class="eyebrow">Nächste Abholung</div>
        <div class="hero-what">${first.map((p) => esc(catName(p.category))).join(" & ")}</div>
        <div class="hero-date">${fmtLong(first[0].date)} · ${esc([...new Set(first.map((p) => p.provider))].join(", "))}${first.some((p) => p.moved_from) ? ` · <span class="moved-note">verschoben</span>` : ""}</div>
      </div>
      <div class="count${n <= 1 ? " word" : ""}">${count}</div>
    </div>`;
  const list = rest.length ? `<div class="hero-list">${rest.map((p) => `<div class="hl-row" style="--c: var(--c-${p.category})">${tile(p.category)}
      <div class="hl-text"><div class="hl-what">${esc(catName(p.category))}</div><div class="hl-date">${fmtLong(p.date)}${moved(p)}</div></div>
      <span class="rel">${relativeDay(p.date)}</span></div>`).join("")}</div>` : "";
  $("next").classList.toggle("single", !rest.length);
  $("next").innerHTML = hero + list;
}

function renderLegend() {
  const html = state.config.categories.map((c) => `<span class="chip">${tile(c)}${esc(catName(c))}</span>`);
  html.push(`<span class="legend-moved"><span class="moved-mark"></span>Feiertagsverschiebung</span>`);
  $("legend").innerHTML = html.join("");
}

function renderMonths() {
  const byDay = new Map();
  for (const p of visiblePickups()) {
    if (!p.date.startsWith(String(selectedYear))) continue;
    if (!byDay.has(p.date)) byDay.set(p.date, []);
    byDay.get(p.date).push(p);
  }
  const today = iso(new Date());
  const now = new Date();
  // Day fill: one waste type = its tint, two = split diagonally, more = first two (dots in the tooltip tell the rest).
  const fillOf = (ps) => {
    const cols = ps.slice(0, 2).map((p) => `color-mix(in srgb, var(--c-${p.category}) var(--day-tint), transparent)`);
    return cols.length === 2 ? `linear-gradient(135deg, ${cols[0]} 50%, ${cols[1]} 50%)` : cols[0] || "";
  };
  let html = "";
  for (let m = 0; m < 12; m++) {
    const first = new Date(selectedYear, m, 1);
    const days = new Date(selectedYear, m + 1, 0).getDate();
    let g = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((w) => `<div class="wd">${w}</div>`).join("");
    g += "<div></div>".repeat((first.getDay() + 6) % 7);
    for (let d = 1; d <= days; d++) {
      const key = iso(new Date(selectedYear, m, d));
      const ps = byDay.get(key) || [];
      const cls = ["day", ps.length ? "has" : "", key === today ? "today" : "", key < today ? "past" : "", ps.some((p) => p.moved_from) ? "moved" : ""].filter(Boolean).join(" ");
      const attrs = ps.length
        ? ` data-date="${key}" tabindex="0" style="--fill: ${fillOf(ps)}" aria-label="${esc(`${fmtDate(key)}: ${ps.map((p) => catName(p.category) + (p.moved_from ? " (verschoben)" : "")).join(", ")}`)}"`
        : "";
      g += `<div class="${cls}"${attrs}>${d}</div>`;
    }
    const isCur = selectedYear === now.getFullYear() && m === now.getMonth();
    const isDone = selectedYear < now.getFullYear() || (selectedYear === now.getFullYear() && m < now.getMonth());
    const isEarlier = isDone && selectedYear === now.getFullYear();
    html += `<section class="month${isCur ? " cur" : ""}${isDone ? " done" : ""}${isEarlier ? " earlier" : ""}"><h3>${MONTHS[m]}</h3><div class="grid">${g}</div></section>`;
  }
  // Im laufenden Jahr sind vergangene Monate eingeklappt; eine Zeile davor blendet sie ein.
  const earlier = selectedYear === now.getFullYear() ? now.getMonth() : 0;
  if (earlier > 0) {
    const range = earlier === 1 ? MONTHS[0] : `${MONTHS[0]} – ${MONTHS[earlier - 1]}`;
    html = `<button type="button" class="ghost earlier-toggle" id="earlier-toggle" aria-expanded="false" data-range="${range}"></button>` + html;
  }
  dayIndex = byDay;
  hideTip();
  $("months").innerHTML = html;
  if (earlier > 0) setEarlier(showEarlier);
  renderPlanner(byDay);
}

function setEarlier(show) {
  showEarlier = show;
  const btn = $("earlier-toggle");
  $("months").classList.toggle("show-earlier", show);
  btn.setAttribute("aria-expanded", String(show));
  btn.textContent = `${btn.dataset.range} ${show ? "ausblenden" : "anzeigen"}`;
}

// ---------- print: year planner (one column per month, room to write) ----------
function easterSunday(y) {
  // Gauss/Meeus algorithm for the Gregorian calendar
  const a = y % 19, b = Math.floor(y / 100), c = y % 100, d = Math.floor(b / 4), e = b % 4;
  const f = Math.floor((b + 8) / 25), g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30, i = Math.floor(c / 4), k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7, m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31), day = ((h + l - 7 * m + 114) % 31) + 1;
  return new Date(y, month - 1, day);
}

function berlinHolidays(y) {
  const e = easterSunday(y);
  const rel = (n) => iso(new Date(y, e.getMonth(), e.getDate() + n));
  return new Map([
    [`${y}-01-01`, "Neujahr"], [`${y}-03-08`, "Frauentag"], [rel(-2), "Karfreitag"], [rel(1), "Oster\u00admontag"],
    [`${y}-05-01`, "Tag der Arbeit"], [rel(39), "Himmel\u00adfahrt"], [rel(50), "Pfingst\u00admontag"],
    [`${y}-10-03`, "Dt. Einheit"], [`${y}-12-25`, "1. Weih\u00adnachten"], [`${y}-12-26`, "2. Weih\u00adnachten"],
  ]);
}

function isoWeek(date) {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay() || 7));
  return Math.ceil(((d - Date.UTC(d.getUTCFullYear(), 0, 1)) / 864e5 + 1) / 7);
}

function renderPlanner(byDay) {
  const y = selectedYear;
  const holidays = berlinHolidays(y);
  let html = "";
  for (let m = 0; m < 12; m++) {
    const days = new Date(y, m + 1, 0).getDate();
    let rows = "";
    for (let d = 1; d <= 31; d++) {
      if (d > days) { rows += `<div class="pl-row pl-none"></div>`; continue; }
      const date = new Date(y, m, d);
      const key = iso(date);
      const wd = date.getDay();
      const hol = holidays.get(key);
      const cls = ["pl-row", wd === 0 || wd === 6 ? "pl-we" : "", wd === 1 ? "pl-mo" : "", hol ? "pl-hol" : ""].join(" ");
      const dots = (byDay.get(key) || []).map((p) => `<span class="dot${p.moved_from ? " moved" : ""}" style="--c: var(--c-${p.category})"></span>`).join("");
      const kw = wd === 1 ? `<span class="pl-kw">${isoWeek(date)}</span>` : "";
      rows += `<div class="${cls}"><span class="pl-d">${d}</span><span class="pl-wd">${WEEKDAYS[wd]}</span>`
        + `<span class="pl-dots">${dots}</span><span class="pl-note">${hol ? esc(hol) : ""}</span>${kw}</div>`;
    }
    html += `<section class="pl-month"><h3>${MONTHS[m]}</h3>${rows}</section>`;
  }
  $("planner").innerHTML = html;
}

// ---------- day tooltip ----------
let dayIndex = new Map();
let tipFor = null;

function relativeDay(dateIso) {
  const days = Math.round((parseIso(dateIso) - parseIso(iso(new Date()))) / 864e5);
  if (days === 0) return "Heute";
  if (days === 1) return "Morgen";
  if (days === -1) return "Gestern";
  return days > 0 ? `in ${days} Tagen` : `vor ${-days} Tagen`;
}

function tipHtml(dateIso) {
  const items = (dayIndex.get(dateIso) || []).map((p) => {
    const extra = p.moved_from
      ? `<div class="tip-moved">Verschoben vom ${fmtDate(p.moved_from)}</div>`
      : p.note ? `<div class="tip-note">${esc(p.note)}</div>` : "";
    return `<li style="--c: var(--c-${p.category})">
      <span class="dot${p.moved_from ? " moved" : ""}"></span>
      <div><div class="tip-name">${esc(catName(p.category))}</div>
      <div class="tip-provider">${esc(p.provider)}</div>${extra}</div>
    </li>`;
  }).join("");
  return `<div class="tip-head"><span>${fmtDate(dateIso)}</span><span class="tip-rel">${relativeDay(dateIso)}</span></div><ul>${items}</ul>`;
}

function showTip(cell) {
  const tip = $("tip");
  tipFor = cell;
  tip.innerHTML = tipHtml(cell.dataset.date);
  tip.hidden = false;
  // Prefer below the cell, flip above if there is no room; keep inside the viewport.
  const r = cell.getBoundingClientRect();
  const t = tip.getBoundingClientRect();
  const margin = 8;
  let left = r.left + r.width / 2 - t.width / 2;
  left = Math.max(margin, Math.min(left, window.innerWidth - t.width - margin));
  let top = r.bottom + 6;
  if (top + t.height > window.innerHeight - margin) top = r.top - t.height - 6;
  tip.style.left = `${left + window.scrollX}px`;
  tip.style.top = `${top + window.scrollY}px`;
}

function hideTip() {
  tipFor = null;
  const tip = $("tip");
  if (tip) tip.hidden = true;
}

function initTooltip() {
  const months = $("months");
  const cellOf = (e) => e.target.closest(".day[data-date]");
  months.addEventListener("mouseover", (e) => { const c = cellOf(e); if (c && c !== tipFor) showTip(c); });
  months.addEventListener("mouseout", (e) => {
    const c = cellOf(e);
    if (c && !c.contains(e.relatedTarget) && document.activeElement !== c) hideTip();
  });
  months.addEventListener("focusin", (e) => { const c = cellOf(e); if (c) showTip(c); });
  months.addEventListener("focusout", hideTip);
  // Touch: tap a day to show, tap again or elsewhere to hide. Whether the tip
  // was already open must be read on pointerdown, because the tap also focuses
  // the cell (focusin opens the tip) before the click event arrives.
  let wasOpen = false;
  months.addEventListener("pointerdown", (e) => { const c = cellOf(e); wasOpen = !!c && tipFor === c; });
  months.addEventListener("click", (e) => {
    const c = cellOf(e);
    if (!c) return;
    if (wasOpen && e.pointerType !== "mouse") { hideTip(); c.blur(); } else showTip(c);
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".day[data-date]")) hideTip(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideTip(); });
  window.addEventListener("scroll", () => { if (tipFor) showTip(tipFor); }, { passive: true });
  window.addEventListener("resize", hideTip);
}

// ---------- settings dialog ----------
function openSettings() {
  const cfg = state.config;
  pendingAddress = cfg.address;
  $("welcome").hidden = !!cfg.address;
  $("addr-current").textContent = cfg.address ? `Aktuell: ${cfg.address.label}` : "";
  $("addr-results").innerHTML = "";
  $("addr-error").textContent = "";
  $("settings-error").textContent = "";
  $("cats").innerHTML = Object.entries(state.categories).map(([code, name]) =>
    `<label class="radio"><input type="checkbox" value="${code}" ${cfg.categories.includes(code) ? "checked" : ""}>
      <span class="sw" style="display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--c-${code})"></span>${esc(name)}</label>`).join("");
  const mode = cfg.paper.mode;
  document.querySelectorAll('input[name="paper"]').forEach((r) => { r.checked = r.value === mode; });
  $("portal-hint").textContent = state.portal_configured
    ? "Zugangsdaten sind auf dem Server hinterlegt."
    : "Dafür müssen BR_USERNAME und BR_PASSWORD in der .env-Datei auf dem Server stehen.";
  $("first-date").value = cfg.paper.first_date || "";
  $("interval").value = cfg.paper.interval_weeks || 4;
  updateManualRow();
  $("notify-time").value = cfg.notify_time || "18:00";
  $("dlg-settings").showModal();
  renderPush();
}

function updateManualRow() {
  const manual = document.querySelector('input[name="paper"]:checked')?.value === "manual";
  $("manual-row").style.display = manual ? "" : "none";
}

async function searchAddress() {
  const street = $("street").value.trim();
  const number = $("number").value.trim();
  $("addr-error").textContent = "";
  $("addr-results").innerHTML = "";
  if (!street || !number) { $("addr-error").textContent = "Straße und Hausnummer eingeben."; return; }
  $("btn-search").disabled = true;
  try {
    const results = await api(`/api/address/search?street=${encodeURIComponent(street)}&number=${encodeURIComponent(number)}`);
    if (!results.length) { $("addr-error").textContent = "Keine Adresse gefunden. Schreibweise prüfen."; return; }
    $("addr-results").innerHTML = results.map((r, i) => `<button type="button" data-i="${i}">${esc(r.label)}</button>`).join("");
    $("addr-results").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
      pendingAddress = results[Number(b.dataset.i)];
      $("addr-results").querySelectorAll("button").forEach((x) => x.classList.toggle("selected", x === b));
      $("addr-current").textContent = `Ausgewählt: ${pendingAddress.label}`;
    }));
    if (results.length === 1) $("addr-results").querySelector("button").click();
  } catch (e) {
    $("addr-error").textContent = e.message;
  } finally {
    $("btn-search").disabled = false;
  }
}

async function saveSettings(ev) {
  ev.preventDefault();
  $("settings-error").textContent = "";
  if (!pendingAddress) { $("settings-error").textContent = "Bitte eine Adresse suchen und auswählen."; return; }
  const categories = [...$("cats").querySelectorAll("input:checked")].map((i) => i.value);
  if (!categories.length) { $("settings-error").textContent = "Mindestens eine Müllart auswählen."; return; }
  const mode = document.querySelector('input[name="paper"]:checked')?.value || "off";
  const paper = { mode, first_date: $("first-date").value || null, interval_weeks: Number($("interval").value) || 4 };
  if (mode === "manual" && !paper.first_date) { $("settings-error").textContent = "Datum einer bekannten Papier-Abholung angeben."; return; }
  $("btn-save").disabled = true;
  $("btn-save").textContent = "Speichere…";
  try {
    const notify_time = $("notify-time").value || "18:00";
    state = await api("/api/config", { method: "PUT", body: JSON.stringify({ address: pendingAddress, categories, paper, notify_time }) });
    offlineSince = null;
    $("dlg-settings").close();
    render();
  } catch (e) {
    $("settings-error").textContent = e.message;
  } finally {
    $("btn-save").disabled = false;
    $("btn-save").textContent = "Speichern";
  }
}

// ---------- push reminders ----------
const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const pushAvailable = () => window.isSecureContext && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

async function swRegistration() {
  return (await navigator.serviceWorker.getRegistration("/")) || navigator.serviceWorker.register("/sw.js");
}

async function currentPushSub() {
  if (!pushAvailable()) return null;
  const reg = await navigator.serviceWorker.getRegistration("/");
  return reg ? reg.pushManager.getSubscription() : null;
}

function b64urlToBytes(s) {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const bin = atob((s + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function renderPush() {
  const box = $("push-on");
  const hint = $("push-hint");
  $("push-error").textContent = "";
  let why = "";
  if (!window.isSecureContext) why = "Push geht nur, wenn die App über ihre HTTPS-Adresse geöffnet wird (siehe Anleitung im README).";
  else if (isIOS && !isStandalone()) why = "Auf dem iPhone zuerst die App zum Home-Bildschirm hinzufügen: Teilen-Symbol → „Zum Home-Bildschirm“. Dann die App über das neue Symbol öffnen und hier einschalten.";
  else if (!pushAvailable()) why = "Dieser Browser unterstützt keine Push-Benachrichtigungen.";
  else if (Notification.permission === "denied") why = "Mitteilungen sind für diese App blockiert. In den Einstellungen des Geräts unter „Mitteilungen“ erlauben.";
  box.disabled = !!why || offlineSince !== null;
  hint.textContent = why;
  const sub = why ? null : await currentPushSub().catch(() => null);
  box.checked = !!sub;
  $("btn-push-test").hidden = !sub;
}

async function togglePush() {
  const box = $("push-on");
  const on = box.checked;
  $("push-error").textContent = "";
  box.disabled = true;
  try {
    if (on) {
      // Muss direkt aus dem Antippen heraus passieren, sonst fragt iOS nicht.
      const perm = await Notification.requestPermission();
      if (perm !== "granted") throw new Error("Ohne Erlaubnis für Mitteilungen geht es nicht.");
      const reg = await swRegistration();
      await navigator.serviceWorker.ready;
      const { public_key } = await api("/api/push/key");
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64urlToBytes(public_key) });
      await api("/api/push/subscribe", { method: "POST", body: JSON.stringify(sub.toJSON()) });
    } else {
      const sub = await currentPushSub();
      if (sub) {
        await api("/api/push/unsubscribe", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) }).catch(() => {});
        await sub.unsubscribe();
      }
    }
  } catch (e) {
    $("push-error").textContent = e.message;
  }
  await renderPush();
}

async function testPush() {
  const btn = $("btn-push-test");
  $("push-error").textContent = "";
  btn.disabled = true;
  try {
    const sub = await currentPushSub();
    if (!sub) throw new Error("Auf diesem Gerät sind Erinnerungen nicht eingeschaltet.");
    await api("/api/push/test", { method: "POST", body: JSON.stringify({ endpoint: sub.endpoint }) });
    btn.textContent = "Gesendet";
  } catch (e) {
    $("push-error").textContent = e.message;
  } finally {
    setTimeout(() => { btn.textContent = "Test senden"; btn.disabled = false; }, 1500);
  }
}

// ---------- subscribe dialog ----------
function icsUrl() {
  return `${location.origin}/api/calendar.ics${$("ics-reminder").checked ? "?reminder=true" : ""}`;
}
function updateIcs() {
  $("ics-url").value = icsUrl();
  $("ics-download").href = icsUrl();
}

// ---------- actions ----------
// iOS ignoriert window.print() in Apps vom Home-Bildschirm. Dort an Safari weiterreichen
// (Schema x-safari-https:, ab iOS 17), Safari druckt dann beim Laden (siehe init).
function printPlanner() {
  if (!(isIOS && isStandalone())) { window.print(); return; }
  const url = new URL(`/?print=${selectedYear}`, location.href);
  $("print-safari").href = `x-safari-${url.href}`;
  $("dlg-print").showModal();
}
async function refresh() {
  if (!state.config.address) { openSettings(); return; }
  const btn = $("btn-refresh");
  btn.disabled = true;
  btn.classList.add("busy");
  $("btn-refresh-label").textContent = "Lade…";
  try {
    state = await api("/api/refresh", { method: "POST" });
    offlineSince = null;
    render();
  } catch (e) {
    if (e.message === OFFLINE_MSG && offlineSince !== null) { renderStatus(); return; } // Hinweis mit Stand bleibt
    $("banner").hidden = false;
    $("banner").classList.toggle("offline", e.message === OFFLINE_MSG);
    $("banner").textContent = e.message;
  } finally {
    btn.disabled = false;
    btn.classList.remove("busy");
    $("btn-refresh-label").textContent = "Aktualisieren";
  }
}

async function init() {
  initTooltip();
  $("btn-refresh").addEventListener("click", refresh);
  $("btn-settings").addEventListener("click", openSettings);
  $("address").addEventListener("click", openSettings);
  $("btn-print").addEventListener("click", printPlanner);
  $("btn-subscribe").addEventListener("click", () => { updateIcs(); $("dlg-subscribe").showModal(); });
  $("ics-reminder").addEventListener("change", updateIcs);
  $("btn-copy").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(icsUrl()); $("btn-copy").textContent = "Kopiert"; }
    catch { $("ics-url").select(); }
    setTimeout(() => { $("btn-copy").textContent = "Kopieren"; }, 1500);
  });
  const stepYear = (delta) => {
    const i = availableYears.indexOf(selectedYear) + delta;
    if (i < 0 || i >= availableYears.length) return;
    selectedYear = availableYears[i];
    renderYears();
    renderMonths();
  };
  $("months").addEventListener("click", (e) => { if (e.target.closest("#earlier-toggle")) setEarlier(!showEarlier); });
  $("year-prev").addEventListener("click", () => stepYear(-1));
  $("year-next").addEventListener("click", () => stepYear(1));
  $("btn-search").addEventListener("click", searchAddress);
  $("number").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchAddress(); } });
  $("street").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("number").focus(); } });
  $("settings-form").addEventListener("submit", saveSettings);
  $("btn-cancel").addEventListener("click", () => $("dlg-settings").close());
  document.querySelectorAll('input[name="paper"]').forEach((r) => r.addEventListener("change", updateManualRow));
  $("push-on").addEventListener("change", togglePush);
  $("btn-push-test").addEventListener("click", testPush);

  // Service Worker: App ohne Serververbindung anzeigen und Push empfangen.
  // Geht nur über HTTPS (oder localhost); sonst läuft die App wie bisher.
  if (window.isSecureContext && "serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }
  // Zurück aus dem Hintergrund (z. B. wieder im WLAN): Stand neu laden.
  const reload = async () => {
    if (document.visibilityState !== "visible" || !state) return;
    try { await loadState(); render(); } catch { /* bleibt beim angezeigten Stand */ }
  };
  document.addEventListener("visibilitychange", reload);
  window.addEventListener("online", reload);

  try {
    await loadState();
  } catch (e) {
    $("banner").hidden = false;
    $("banner").classList.add("offline");
    $("banner").textContent = e.message;
    return;
  }
  // Aus der iPhone-App nach Safari weitergereicht (?print=<Jahr>): Jahr wählen und gleich drucken.
  const printYear = Number(new URLSearchParams(location.search).get("print"));
  if (printYear) {
    selectedYear = printYear;
    history.replaceState(null, "", location.pathname);
  }
  render();
  if (printYear) { setTimeout(() => window.print(), 300); return; }
  if (!state.config.address && offlineSince === null) openSettings();
}

init();
