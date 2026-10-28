import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./landing.css";
import "./workspace.css";
import "./workspace/integration.css";
import "./workspace/mvp.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
