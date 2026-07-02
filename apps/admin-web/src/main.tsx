import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

function App() {
  return (
    <div style={{ padding: "2rem", fontFamily: "system-ui, sans-serif" }}>
      <h1>RMP — Центр управления рекламой</h1>
      <p>Phase 1 skeleton. Business pages will be added in later phases.</p>
      <p>
        API: <code>/api/v1/</code> (Control API on :8000)
        {" | "}
        Devices: <code>/device/v1/</code> (Device Gateway on :8001)
      </p>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
