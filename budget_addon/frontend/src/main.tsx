import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App";
import { ThemeProvider } from "./theme";
import "./app.css";

const container = document.getElementById("root");
if (!container) {
  throw new Error("root elemanı bulunamadı");
}

createRoot(container).render(
  <StrictMode>
    <ThemeProvider><App /></ThemeProvider>
  </StrictMode>,
);
