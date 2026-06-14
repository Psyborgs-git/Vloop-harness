import { StrictMode } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css"; // We'll create or reuse a premium global css

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <BrowserRouter basename="/control-pane.html">
      <App />
    </BrowserRouter>
  </StrictMode>
);
