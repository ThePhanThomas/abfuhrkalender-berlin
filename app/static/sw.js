"use strict";
// Service Worker: zeigt die App auch ohne Serververbindung (letzter Stand) und
// empfängt Push-Erinnerungen. Wird unter /sw.js ausgeliefert, damit er für die
// ganze Seite gilt.

const CACHE = "abfuhrkalender-v1";
const SHELL = [
  "/",
  "/static/app.css",
  "/static/app.js",
  "/static/icon.svg",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/apple-touch-icon.png",
];
// Nur diese Adressen werden zwischengespeichert. Alles andere (Adresssuche,
// Speichern, Aktualisieren) geht immer direkt an den Server.
const CACHED = (path) => path === "/" || path === "/api/state" || path.startsWith("/static/");
// Ohne Heimnetz/VPN antwortet der Server gar nicht – nicht ewig warten.
const TIMEOUT_MS = 5000;

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    // Seitenaufrufe (mode "navigate") lassen sich nicht mit Optionen weiterreichen,
    // deshalb die Adresse neu abrufen statt des Request-Objekts.
    const response = await fetch(request.url, { signal: ctrl.signal, cache: "no-cache", credentials: "same-origin" });
    if (response.ok) {
      // Zeitpunkt mitspeichern, damit die Seite offline „Stand vom …“ zeigen kann.
      const headers = new Headers(response.headers);
      headers.set("X-Cached-At", new Date().toISOString());
      const copy = new Response(await response.clone().blob(), { status: response.status, headers });
      await cache.put(request.url, copy);
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request.url, { ignoreSearch: true });
    if (!cached) throw err;
    const headers = new Headers(cached.headers);
    headers.set("X-Offline", "1");
    return new Response(await cached.blob(), { status: 200, headers });
  } finally {
    clearTimeout(timer);
  }
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== "GET" || url.origin !== self.location.origin || !CACHED(url.pathname)) return;
  event.respondWith(networkFirst(event.request));
});

// ---------- Push ----------
self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = { body: event.data && event.data.text() }; }
  event.waitUntil(self.registration.showNotification(data.title || "Abfuhrkalender", {
    body: data.body || "",
    tag: data.tag || "abfuhr",
    icon: "/static/icons/icon-192.png",
    badge: "/static/icons/icon-192.png",
    data: { url: "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) if ("focus" in w) return w.focus();
    return self.clients.openWindow("/");
  })());
});
