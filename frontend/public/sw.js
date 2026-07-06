// TOMBSTONE — feat-65 hot-fix.
//
// La versión anterior de este SW causaba loop de RSC en /sign-in y
// /dashboard. Esta versión se auto-desregistra y limpia todos los
// caches al primer ciclo activate. Sin fetch listener, Chrome no
// intercepta requests — la app carga como web normal.
//
// Cuando Chrome actualice a esta versión (chequea updates cada 24 h,
// o al primer navigation reload), el SW viejo se reemplaza por este,
// que se autoelimina y desaparece. Con el nuevo PwaRegister que ya
// tampoco registra nada, no vuelve a instalarse.

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Borrar todos los caches que dejó la versión vieja.
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      // Desregistrar este SW mismo.
      await self.registration.unregister();
      // Recargar clientes conectados para que carguen sin SW.
      const clients = await self.clients.matchAll({ type: "window" });
      clients.forEach((c) => {
        try {
          c.navigate(c.url);
        } catch {
          /* algunos browsers no permiten navigate desde SW; ignoramos */
        }
      });
    })(),
  );
});

// SIN `fetch` listener a propósito: Chrome no intercepta requests.
