import { Routes, Route, useLocation } from "react-router-dom";
import { useEffect } from "react";

import DynamicLoader from "./DynamicLoader";
import { useRouteStore } from "./store";
import Homepage from "./Homepage";

function CatchAllRoute() {
    const location = useLocation();

    // If we're at the root, render the Homepage component
    if (location.pathname === "/") {
        return <Homepage />;
    }

    // Sanitize path: remove leading slash
    const path = location.pathname.replace(/^\/+/, '');

    const versions = useRouteStore((state) => state.versions);
    // Use the timestamp from the store, or fallback to an initial baseline timestamp if none is set
    const version = versions[path] || 1;

    return <DynamicLoader routePath={path} version={version} />;
}

export default function App() {
    const updateVersion = useRouteStore((state) => state.updateVersion);

    useEffect(() => {
        const wsUrl = import.meta.env.VITE_WS_URL;
        if (!wsUrl) {
            console.warn("VITE_WS_URL is not set. Real-time updates are disabled.");
            return;
        }

        let ws: WebSocket;
        let reconnectTimer: number;

        function connect() {
            try {
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {
                    console.log("WebSocket connection established");
                };

                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.event === "module_updated" && data.path) {
                            console.log(`Module updated: ${data.path}`);
                            // Remove leading slash if present to match our sanitized path format
                            const sanitizedPath = data.path.replace(/^\/+/, '');
                            updateVersion(sanitizedPath, Date.now());
                        }
                    } catch (e) {
                        console.error("Error parsing WebSocket message:", e);
                    }
                };

                ws.onclose = () => {
                    console.log("WebSocket connection closed, reconnecting...");
                    reconnectTimer = window.setTimeout(connect, 3000);
                };

                ws.onerror = (err) => {
                    console.error("WebSocket error:", err);
                    ws.close();
                };
            } catch (err) {
                console.error("Error establishing WebSocket:", err);
                reconnectTimer = window.setTimeout(connect, 3000);
            }
        }

        connect();

        return () => {
            clearTimeout(reconnectTimer);
            if (ws) {
                ws.close();
            }
        };
    }, [updateVersion]);

    return (
        <Routes>
            <Route path="*" element={<CatchAllRoute />} />
        </Routes>
    );
}
