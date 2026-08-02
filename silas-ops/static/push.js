// Registers the service worker and subscribes to push, using the VAPID
// public key served at /push/vapid-public-key. Called once from the daily
// view. Silently no-ops if push isn't supported or the key isn't set up
// yet (VAPID keys are a one-time `python -m src.cli push-keys` step).
async function initPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  const keyRes = await fetch("/push/vapid-public-key");
  const { key } = await keyRes.json();
  if (!key) return;

  const reg = await navigator.serviceWorker.register("/static/sw.js");
  const existing = await reg.pushManager.getSubscription();
  if (existing) return;

  const perm = await Notification.requestPermission();
  if (perm !== "granted") return;

  const sub = await reg.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(key),
  });
  await fetch("/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub.toJSON()),
  });
}

function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

initPush().catch(() => {});
