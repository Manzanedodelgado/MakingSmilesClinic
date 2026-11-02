// Kill-switch: si algún navegador tiene registrado un Service Worker antiguo de este
// origen (de una prueba PWA pasada, ya sin código de registro en la app actual), este
// fichero lo sustituye y se autodestruye — se desregistra y borra toda su caché, para
// que ese navegador vuelva a depender siempre del servidor real, nunca de una copia
// suya propia. Encontrado 26-sep-2026: logs de Caddy con peticiones repetidas a /sw.js
// con cabecera Service-Worker: script desde un cliente real — señal de que hay (o hubo)
// un SW activo sirviendo contenido sin pasar por el servidor.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      await self.registration.unregister();
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((client) => client.navigate(client.url));
    })()
  );
});
