/**
 * Telegram Mini App köprüsü.
 *
 * Uygulama Telegram dışında (Home Assistant paneli, tarayıcı) da çalıştığı
 * için her çağrı isteğe bağlıdır: `telegram()` `undefined` dönerse arayüz
 * kendi varsayılan temasıyla çalışmaya devam eder.
 *
 * `initDataUnsafe` yalnızca gösterim amaçlı okunur; kimlik doğrulama her zaman
 * sunucuda, imzalı `initData` üzerinden yapılır.
 */

interface TelegramWebApp {
  initData: string;
  colorScheme: "light" | "dark";
  themeParams: Record<string, string>;
  ready: () => void;
  expand: () => void;
  HapticFeedback?: {
    notificationOccurred: (type: "error" | "success" | "warning") => void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

export function telegram(): TelegramWebApp | undefined {
  return window.Telegram?.WebApp;
}

export function isInsideTelegram(): boolean {
  return Boolean(telegram()?.initData);
}

/** Telegram tema renklerini CSS degiskenlerine aktarir. */
export function applyTelegramTheme(): void {
  const app = telegram();
  if (!app) return;

  app.ready();
  app.expand();

  const root = document.documentElement;
  const mapping: Record<string, string> = {
    bg_color: "--tg-bg",
    secondary_bg_color: "--tg-surface",
    text_color: "--tg-text",
    hint_color: "--tg-hint",
    link_color: "--tg-link",
    button_color: "--tg-button",
    button_text_color: "--tg-button-text",
    destructive_text_color: "--tg-danger",
  };

  for (const [key, variable] of Object.entries(mapping)) {
    const value = app.themeParams?.[key];
    if (value) root.style.setProperty(variable, value);
  }
  root.dataset.theme = app.colorScheme;
}

export function haptic(type: "error" | "success" | "warning"): void {
  telegram()?.HapticFeedback?.notificationOccurred(type);
}
