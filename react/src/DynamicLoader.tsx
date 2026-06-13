import React, { Suspense, useMemo } from "react";
import { CircularProgress, Box, Typography } from "@mui/material";
import { ErrorBoundary } from "./ErrorBoundary";

function PageNotYetGenerated({ routePath }: { routePath: string }) {
    return (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 2 }}>
            <Typography variant="h5" color="text.secondary">Page Not Yet Generated</Typography>
            <Typography color="text.secondary">Path: {routePath}</Typography>
        </Box>
    );
}

function loadDynamicScreen(path: string, version: number) {
    const backendUrl = import.meta.env.VITE_API_URL || "";
    // Clean up backendUrl if it ends with slash
    const base = backendUrl.replace(/\/+$/, '');

    return React.lazy(() =>
        import(/* @vite-ignore */ `${base}/public/${path}.js?v=${version}`)
            .catch((err) => {
                console.error(`Failed to load module for path ${path}:`, err);
                // Return a fake module that renders the 404/Not Generated UI
                return {
                    default: () => <PageNotYetGenerated routePath={path} />
                };
            })
    );
}

export default function DynamicLoader({ routePath, version }: { routePath: string, version: number }) {
    // Memoize the dynamically imported component based on path and version.
    // If version changes, useMemo will recreate the Lazy component, triggering a new import.
    const DynamicComponent = useMemo(() => loadDynamicScreen(routePath, version), [routePath, version]);

    return (
        <ErrorBoundary>
            <Suspense
                fallback={
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100vh', gap: 2 }}>
                        <CircularProgress />
                        <Typography color="text.secondary">Loading component...</Typography>
                    </Box>
                }
            >
                <DynamicComponent routePath={routePath} />
            </Suspense>
        </ErrorBoundary>
    );
}
