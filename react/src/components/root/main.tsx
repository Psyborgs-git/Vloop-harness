import React from "react";
import { createRoot } from "react-dom/client";
import { HarnessProvider } from "@harness/HarnessProvider";
import App from "./App";

createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <HarnessProvider>
            <App />
        </HarnessProvider>
    </React.StrictMode>
);
