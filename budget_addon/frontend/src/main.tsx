import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { ThemeProvider } from "./theme";
import "./app.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("root elemanı bulunamadı");
}

// Servis çalışanı uygulamanın kabuğunu saklar; internet yokken de site açılır
// ve hızlı giriş kuyruğa yazılabilir. Home Assistant panelinde (Ingress) adres
// oturuma göre değiştiği için kaydedilmez.
if (
  "serviceWorker" in navigator &&
  window.isSecureContext &&
  !window.location.pathname.includes("hassio_ingress")
) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("sw.js").catch(() => undefined);
  });
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider><App /></ThemeProvider>
  </StrictMode>,
);
