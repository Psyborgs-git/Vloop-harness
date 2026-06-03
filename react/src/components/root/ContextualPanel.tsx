/**
 * ContextualPanel — a right-side drawer that hosts secondary tool panels.
 *
 * On desktop (≥ md) it slides in from the right at 360 px wide.
 * On mobile (< md) it opens as a full-height bottom sheet.
 *
 * Content is driven by the `panelType` prop:
 *   "dspy"      — DSPy component browser
 *   "pipelines" — Pipeline editor
 *   "tools"     — Terminal / Filesystem / Policy tools
 *   "view"      — Generated React view preview + source
 */

import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import {
    Box,
    Drawer,
    IconButton,
    Tab,
    Tabs,
    Tooltip,
    Typography,
    useMediaQuery,
    useTheme,
} from "@mui/material";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useEffect, useState } from "react";

import * as api from "./api";
import AgentRunPanel from "./AgentRunPanel";
import AgentRunTimeline from "./AgentRunTimeline";
import AppManifestPanel from "./AppManifestPanel";
import DSPyPanel from "./DSPyPanel";
import EvalPanel from "./EvalPanel";
import PipelinePanel from "./PipelinePanel";
import ToolsPanel from "./ToolsPanel";
import type { ContextPanelType, GeneratedView } from "./types";

interface Props {
    open: boolean;
    panelType: ContextPanelType;
    panelId?: string;
    onClose: () => void;
}

const DRAWER_WIDTH = 360;

export default function ContextualPanel({ open, panelType, panelId, onClose }: Props) {
    const theme = useTheme();
    const isMobile = useMediaQuery(theme.breakpoints.down("md"));

    const anchor = isMobile ? "bottom" : "right";

    const paperSx = isMobile
        ? ({
            height: "92vh",
            borderRadius: "12px 12px 0 0",
            overflow: "hidden",
            display: "flex",
            flexDirection: "column",
        } as const)
        : ({
            width: DRAWER_WIDTH,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
        } as const);

    return (
        <Drawer
            anchor={anchor}
            open={open}
            onClose={onClose}
            PaperProps={{ sx: paperSx }}
            ModalProps={{ keepMounted: false }}
        >
            {/* Header */}
            <Box
                sx={{
                    display: "flex",
                    alignItems: "center",
                    p: 1,
                    pl: 2,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    flexShrink: 0,
                }}
            >
                <Typography variant="subtitle2" fontWeight={600} sx={{ flexGrow: 1 }}>
                    {panelType === "dspy" && "DSPy Components"}
                    {panelType === "pipelines" && "Pipelines"}
                    {panelType === "tools" && "Tools"}
                    {panelType === "view" && "Generated View"}
                    {panelType === "agents" && "Agent Runs"}
                    {panelType === "timeline" && "Agent Run Timeline"}
                    {panelType === "manifests" && "App Manifests"}
                    {panelType === "eval" && "Component Evals"}
                </Typography>
                <Tooltip title="Close panel">
                    <IconButton size="small" onClick={onClose}>
                        <CloseIcon fontSize="small" />
                    </IconButton>
                </Tooltip>
            </Box>

            {/* Content */}
            <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
                {panelType === "dspy" && (
                    <DSPyPanel focusComponentId={panelId} onFocused={() => { }} />
                )}
                {panelType === "pipelines" && (
                    <PipelinePanel focusPipelineId={panelId} onFocused={() => { }} />
                )}
                {panelType === "tools" && <ToolsPanel />}
                {panelType === "view" && panelId && (
                    <ViewPreview viewId={panelId} />
                )}
                {panelType === "agents" && (
                    <AgentRunPanel focusRunId={panelId} onFocused={() => { }} />
                )}
                {panelType === "timeline" && panelId && (
                    <AgentRunTimeline runId={panelId} onClose={onClose} />
                )}
                {panelType === "manifests" && (
                    <AppManifestPanel focusManifestId={panelId} onFocused={() => { }} />
                )}
                {panelType === "eval" && <EvalPanel componentId={panelId} />}
            </Box>
        </Drawer>
    );
}

// ── View preview sub-panel ────────────────────────────────────────────────────

function ViewPreview({ viewId }: { viewId: string }) {
    const [view, setView] = useState<GeneratedView | null>(null);
    const [tab, setTab] = useState<"preview" | "source">("preview");

    useEffect(() => {
        api.listViews().then((views) => {
            const found = views.find((v) => v.id === viewId);
            if (found) setView(found);
        });
    }, [viewId]);

    if (!view) return null;

    return (
        <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
            <Box sx={{ borderBottom: "1px solid", borderColor: "divider", flexShrink: 0 }}>
                <Tabs
                    value={tab}
                    onChange={(_, v) => setTab(v)}
                    textColor="primary"
                    indicatorColor="primary"
                    sx={{ minHeight: 36 }}
                >
                    <Tab value="preview" label="Preview" sx={{ minHeight: 36, textTransform: "none", fontSize: "0.82rem" }} />
                    <Tab value="source" label="Source" sx={{ minHeight: 36, textTransform: "none", fontSize: "0.82rem" }} />
                </Tabs>
            </Box>

            {tab === "preview" && (
                <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", p: 1, gap: 1 }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
                            {view.component_name}
                        </Typography>
                        <Tooltip title="Open in new tab">
                            <IconButton
                                size="small"
                                component="a"
                                href={`/ui/${view.component_name}`}
                                target="_blank"
                                rel="noopener"
                            >
                                <OpenInNewIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                    </Box>
                    <Box
                        component="iframe"
                        src={`/ui/${view.component_name}`}
                        sx={{
                            flexGrow: 1,
                            border: "1px solid",
                            borderColor: "divider",
                            borderRadius: 1,
                            width: "100%",
                        }}
                        title={view.component_name}
                    />
                </Box>
            )}

            {tab === "source" && (
                <Box sx={{ flexGrow: 1, overflow: "auto", p: 1 }}>
                    {view.view_spec && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                            {view.view_spec}
                        </Typography>
                    )}
                    <SyntaxHighlighter
                        language="tsx"
                        style={vscDarkPlus as any}
                        customStyle={{ borderRadius: 6, fontSize: "0.75rem", margin: 0 }}
                    >
                        {view.react_code}
                    </SyntaxHighlighter>
                </Box>
            )}
        </Box>
    );
}
