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

        let ws: WebSocket | null = null;
        let reconnectTimer: number | undefined;
        let isAlive = true;

        function connect() {
            if (!isAlive) return;
            try {
                ws = new WebSocket(wsUrl);

                ws.onopen = () => {
                    console.log("WebSocket connection established");
                };

                ws.onmessage = (event) => {
                    if (!isAlive) return;
                    try {
                        const data = JSON.parse(event.data);
                        if (data.event === "module_updated" && data.path) {
                            console.log(`Module updated: ${data.path}`);
                            const sanitizedPath = data.path.replace(/^\/+/, '');
                            updateVersion(sanitizedPath, Date.now());
                        }
                    } catch (e) {
                        console.error("Error parsing WebSocket message:", e);
                    }
                };

                ws.onclose = () => {
                    if (!isAlive) return;
                    console.log("WebSocket connection closed, reconnecting...");
                    reconnectTimer = window.setTimeout(connect, 3000);
                };

                ws.onerror = (err) => {
                    console.error("WebSocket error:", err);
                    if (ws) {
                        ws.close();
                    }
                };
            } catch (err) {
                console.error("Error establishing WebSocket:", err);
                if (isAlive) {
                    reconnectTimer = window.setTimeout(connect, 3000);
                }
            }
        }

        connect();

        return () => {
            isAlive = false;
            clearTimeout(reconnectTimer);
            if (ws) {
                ws.onclose = null;
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
