/**
 * Bu cihazdaki anlık bildirim aboneliği.
 *
 * Abonelik cihaza ve tarayıcıya aittir. iPhone ve iPad'de Safari yalnızca ana
 * ekrana eklenmiş sitelere bildirim gönderebilir; o durum ayrıca bildirilir ki
 * kişiye neden açılamadığı söylenebilsin.
 */

import { api } from "./api";

export type PushState = "unsupported" | "needs-install" | "denied" | "off" | "on";

const WORKER_URL = "sw.js";

function isAppleMobile(): boolean {
  return (
    /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function isInstalled(): boolean {
  const legacy = (navigator as Navigator & { standalone?: boolean }).standalone;
  return window.matchMedia("(display-mode: standalone)").matches || legacy === true;
}

function keyBytes(base64url: string): Uint8Array {
  const padded = base64url.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(base64url.length / 4) * 4, "=");
  return Uint8Array.from(atob(padded), (character) => character.charCodeAt(0));
}

async function currentSubscription(): Promise<PushSubscription | null> {
  const registration = await navigator.serviceWorker.getRegistration();
  return (await registration?.pushManager.getSubscription()) ?? null;
}

export async function readPushState(): Promise<PushState> {
  if (!window.isSecureContext || !("serviceWorker" in navigator)) return "unsupported";
  if (!("PushManager" in window) || !("Notification" in window)) {
    return isAppleMobile() && !isInstalled() ? "needs-install" : "unsupported";
  }
  if (Notification.permission === "denied") return "denied";
  const subscription = await currentSubscription();
  if (!subscription) return "off";
  // Sunucu aboneligi silmis olabilir (baska kisi bu cihazda giris yapti,
  // bildirim servisi adresi yeniledi); sessizce yeniden bildirilir.
  void api.subscribePush(subscription.toJSON()).catch(() => undefined);
  return "on";
}

export async function enablePush(publicKey: string): Promise<void> {
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Bildirim izni verilmedi.");
  }
  await navigator.serviceWorker.register(WORKER_URL);
  const registration = await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey),
    }));
  await api.subscribePush(subscription.toJSON());
}

export async function disablePush(): Promise<void> {
  const subscription = await currentSubscription();
  if (!subscription) return;
  await api.unsubscribePush(subscription.endpoint).catch(() => undefined);
  await subscription.unsubscribe();
}
