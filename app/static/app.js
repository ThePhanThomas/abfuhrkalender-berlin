"use strict";

const MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
const WEEKDAYS = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
const SOURCE_NAMES = { bsr: "BSR", berlin_recycling: "Berlin Recycling", paper_manual: "Papier (manuell)" };

const $ = (id) => document.getElementById(id);
let state = null;
let selectedYear = null;
let pendingAddress = null;
let availableYears = [];

// ---------- helpers ----------
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseIso = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const fmtDate = (s) => { const d = parseIso(s); return `${WEEKDAYS[d.getDay()]}, ${String(d.getDate()).padStart(2, "0")}.${String(d.getMonth() + 1).padStart(2, "0")}.${d.getFullYear()}`; };
const catName = (c) => (state && state.categories[c]) || c;
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
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
    else { parts.push(`<span class="bad">${esc(label)}: Fehler</span>`); errors.push(`${label}: ${s.error}`); }
  }
  $("status").innerHTML = parts.map((p, i) => (i === 0 ? esc(p) : p)).join(" · ");
  const banner = $("banner");
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
  const tomorrow = iso(new Date(Date.now() + 864e5));
  const next = new Map();
  for (const p of visiblePickups()) {
    if (p.date >= today && !next.has(p.category)) next.set(p.category, p);
  }
  const items = [...next.values()].sort((a, b) => a.date.localeCompare(b.date));
  if (!items.length) {
    $("next").innerHTML = `<p class="empty">${state.config.address ? "Keine kommenden Termine. Daten aktualisieren?" : "Richte zuerst deine Adresse ein."}</p>`;
    return;
  }
  $("next").innerHTML = items.map((p) => {
    const days = Math.round((parseIso(p.date) - parseIso(today)) / 864e5);
    const when = p.date === today ? "Heute" : p.date === tomorrow ? "Morgen" : `in ${days} Tagen`;
    const soon = days <= 1 ? " soon" : "";
    const note = p.moved_from ? " · verschoben" : "";
    return `<div class="card${soon}" style="--c: var(--c-${p.category})">
      <div class="when">${when}</div>
      <div class="what">${esc(catName(p.category))}</div>
      <div class="date">${fmtDate(p.date)}${note}</div>
    </div>`;
  }).join("");
}

function renderLegend() {
  const html = state.config.categories.map((c) => `<span><span class="sw" style="background: var(--c-${c})"></span>${esc(catName(c))}</span>`);
  html.push(`<span><span class="dot moved" style="--c: var(--text-3); display:inline-block; margin-right:6px"></span>Feiertagsverschiebung</span>`);
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
  let html = "";
  for (let m = 0; m < 12; m++) {
    const first = new Date(selectedYear, m, 1);
    const days = new Date(selectedYear, m + 1, 0).getDate();
    let g = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((w) => `<div class="wd">${w}</div>`).join("");
    g += "<div></div>".repeat((first.getDay() + 6) % 7);
    for (let d = 1; d <= days; d++) {
      const key = iso(new Date(selectedYear, m, d));
      const ps = byDay.get(key) || [];
      const cls = ["day", ps.length ? "has" : "", key === today ? "today" : "", key < today ? "past" : ""].join(" ");
      const dots = ps.map((p) => `<span class="dot${p.moved_from ? " moved" : ""}" style="--c: var(--c-${p.category})"></span>`).join("");
      const attrs = ps.length
        ? ` data-date="${key}" tabindex="0" aria-label="${esc(`${fmtDate(key)}: ${ps.map((p) => catName(p.category) + (p.moved_from ? " (verschoben)" : "")).join(", ")}`)}"`
        : "";
      g += `<div class="${cls}"${attrs}>${d}${dots ? `<div class="dots">${dots}</div>` : ""}</div>`;
    }
    html += `<section class="month"><h3>${MONTHS[m]} ${selectedYear}</h3><div class="grid">${g}</div></section>`;
  }
  dayIndex = byDay;
  hideTip();
  $("months").innerHTML = html;
  renderPlanner(byDay);
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
  $("dlg-settings").showModal();
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
    state = await api("/api/config", { method: "PUT", body: JSON.stringify({ address: pendingAddress, categories, paper }) });
    $("dlg-settings").close();
    render();
  } catch (e) {
    $("settings-error").textContent = e.message;
  } finally {
    $("btn-save").disabled = false;
    $("btn-save").textContent = "Speichern";
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
async function refresh() {
  if (!state.config.address) { openSettings(); return; }
  const btn = $("btn-refresh");
  btn.disabled = true;
  btn.classList.add("busy");
  $("btn-refresh-label").textContent = "Lade…";
  try {
    state = await api("/api/refresh", { method: "POST" });
    render();
  } catch (e) {
    $("banner").hidden = false;
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
  $("btn-print").addEventListener("click", () => window.print());
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
  $("year-prev").addEventListener("click", () => stepYear(-1));
  $("year-next").addEventListener("click", () => stepYear(1));
  $("btn-search").addEventListener("click", searchAddress);
  $("number").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); searchAddress(); } });
  $("street").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); $("number").focus(); } });
  $("settings-form").addEventListener("submit", saveSettings);
  $("btn-cancel").addEventListener("click", () => $("dlg-settings").close());
  document.querySelectorAll('input[name="paper"]').forEach((r) => r.addEventListener("change", updateManualRow));

  try {
    state = await api("/api/state");
  } catch (e) {
    $("banner").hidden = false;
    $("banner").textContent = `Server nicht erreichbar: ${e.message}`;
    return;
  }
  render();
  if (!state.config.address) openSettings();
}

init();
