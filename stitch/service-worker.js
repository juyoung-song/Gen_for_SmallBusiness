const CACHE_NAME = "brewgram-shell-v23";
const APP_SHELL = [
  "/stitch/index.html",
  "/stitch/welcome.html",
  "/stitch/archive.html",
  "/stitch/settings.html",
  "/stitch/onboarding-instagram.html",
  "/stitch/1./code.html",
  "/stitch/2./code.html",
  "/stitch/3./code.html",
  "/stitch/4._1/code.html",
  "/stitch/4._2/code.html",
  "/stitch/shared.css",
  "/stitch/shared.js",
  "/stitch/brand-badge.png",
  "/stitch/manifest.webmanifest",
  "/stitch/offline.html",
  "/stitch/icons/icon.svg",
  "/stitch/icons/icon-192.png",
  "/stitch/icons/icon-512.png",
  "/stitch/icons/icon-maskable-512.png",
  "/stitch/icons/apple-touch-icon.png"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    return;
  }

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return;
  }

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          return response;
        })
        .catch(async () => {
          return (
            (await caches.match(request)) ||
            (await caches.match("/stitch/offline.html"))
          );
        })
    );
    return;
  }

  if (!url.pathname.startsWith("/stitch/")) {
    return;
  }

  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) {
        return cached;
      }
      return fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match("/stitch/offline.html"));
    })
  );
});
