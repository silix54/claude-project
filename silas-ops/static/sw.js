// Service worker for push notifications only — no offline caching, since
// this dashboard's whole point is showing live state; a cached shell that
// looks current but isn't would be worse than no PWA install at all.

self.addEventListener("push", (event) => {
  const data = event.data ? event.data.json() : { title: "Ops", body: "" };
  event.waitUntil(
    self.registration.showNotification(data.title || "Ops", {
      body: data.body || "",
      icon: "/static/icon.png",
      badge: "/static/icon.png",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow("/"));
});
