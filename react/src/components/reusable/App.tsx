/**
 * VLoop Harness — Root Dashboard (Chat-First + Workspace Mode)
 *
 * Layout (chat mode — default):
 *  ┌─ TopBar ─────────────────────────────────────────────────────────┐
 *  │  VLoop Harness    [provider status]  [connection]  [⚙ settings]  │
 *  ├─ Main (full width) ──────────────────────────────────────────────┤
 *  │  ChatPanel (session sidebar + conversation)                       │
 *  └──────────────────────────────────────────────────────────────────┘
 *
 * Layout (workspace mode):
 *  ┌─ TopBar ───────────────────────────────────────────────────────────────┐
 *  ├─ Chat sidebar (350 px, collapsible) │ WorkspaceArea (iframe tabs)      │
 *  └────────────────────────────────────────────────────────────────────────┘
 *
 *  Settings opens as a Dialog (desktop) or bottom Drawer ≤80vh (mobile).
 *  DSPy / Pipelines / Tools open as a contextual right Drawer from chat actions.
 */

import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import DashboardIcon from "@mui/icons-material/Dashboard";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import SearchIcon from "@mui/icons-material/Search";
import SettingsIcon from "@mui/icons-material/Settings";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import ViewListIcon from "@mui/icons-material/ViewList";
import ForumIcon from "@mui/icons-material/Forum";
import {
    AppBar,
    Badge,
    Box,
    Chip,
    CssBaseline,
    Dialog,
    DialogContent,
    DialogTitle,
    Drawer,
    IconButton,
    ThemeProvider,
    Toolbar,
    Tooltip,
    Typography,
    createTheme,
    useMediaQuery,
} from "@mui/material";
import { useEffect, useState } from "react";

import { useHarness } from "@harness/useHarness";
import * as api from "./api";
import { AnalyticsProvider, useAnalytics } from "./analytics";
import ChatPanel from "./ChatPanel";
import ChannelsPanel from "./ChannelsPanel";
import CommandPalette from "./CommandPalette";
import type { PaletteNavType } from "./CommandPalette";
import ContextualPanel from "./ContextualPanel";
import SettingsPanel from "./SettingsPanel";
import TabbarTutorial from "./TabbarTutorial";
import { TUTORIAL_STORAGE_KEY } from "./tutorialTranslations";
import type { ContextPanelState, Provider, WorkspaceWindow } from "./types";
import ViewRegistry from "./ViewRegistry";
import WorkspaceArea from "./WorkspaceArea";

// ── MUI dark theme ────────────────────────────────────────────────────────────

const darkTheme = createTheme({
    palette: {
        mode: "dark",
        primary: {
            main: "#6366f1",
            dark: "#4f46e5",
            light: "#818cf8",
        },
        secondary: {
            main: "#ec4899",
            dark: "#db2777",
        },
        background: {
            default: "#0f0f13",
            paper: "#1a1a24",
        },
        divider: "rgba(255,255,255,0.08)",
        text: {
            primary: "#e2e8f0",
            secondary: "#94a3b8",
            disabled: "#475569",
        },
    },
    shape: { borderRadius: 8 },
    typography: {
        fontFamily: '"Inter", "system-ui", sans-serif',
        h6: { fontWeight: 600 },
    },
    components: {
        MuiAppBar: {
            defaultProps: { elevation: 0 },
            styleOverrides: {
                root: {
                    borderBottom: "1px solid rgba(255,255,255,0.08)",
                    backgroundColor: "#0f0f13",
                },
            },
        },
        MuiDrawer: {
            styleOverrides: {
                paper: {
                    backgroundColor: "#13131a",
                    border: "none",
                    borderRight: "1px solid rgba(255,255,255,0.06)",
                },
            },
        },
        MuiListItemButton: {
            styleOverrides: {
                root: {
                    borderRadius: 8,
                    margin: "2px 8px",
                    "&.Mui-selected": {
                        backgroundColor: "rgba(99,102,241,0.2)",
                        "&:hover": { backgroundColor: "rgba(99,102,241,0.28)" },
                    },
                },
            },
        },
        MuiPaper: {
            styleOverrides: {
                root: { backgroundImage: "none" },
            },
        },
    },
});

// ── Root app ──────────────────────────────────────────────────────────────────

const WORKSPACE_STORAGE_KEY = "vloop_workspace_windows";

export default function App() {
    return (
        <AnalyticsProvider>
            <AppContent />
        </AnalyticsProvider>
    );
}

function AppContent() {
    const { connected } = useHarness();
    const analytics = useAnalytics();
    const [defaultProvider, setDefaultProvider] = useState<Provider | null>(null);
    const [settingsOpen, setSettingsOpen] = useState(false);
    const [paletteOpen, setPaletteOpen] = useState(false);
    const [tutorialOpen, setTutorialOpen] = useState(false);
    const [viewRegistryOpen, setViewRegistryOpen] = useState(false);
    const [focusId, setFocusId] = useState<string | null>(null);
    const [contextPanel, setContextPanel] = useState<ContextPanelState>({ type: null });
    const [currentView, setCurrentView] = useState<"chat" | "channels">("chat");

    // ── Workspace state ────────────────────────────────────────────────────────
    const [workspaceMode, setWorkspaceMode] = useState(false);
    const [chatCollapsed, setChatCollapsed] = useState(false);
    const [windows, setWindows] = useState<WorkspaceWindow[]>([]);
    const [focusedWindowId, setFocusedWindowId] = useState<string | null>(null);

    const isMobile = useMediaQuery(darkTheme.breakpoints.down("md"));
    const openWindowCount = windows.filter((w) => !w.minimized).length;

    // ── Load workspace from localStorage ──────────────────────────────────────
    useEffect(() => {
        try {
            const saved = localStorage.getItem(WORKSPACE_STORAGE_KEY);
            if (saved) {
                const parsed = JSON.parse(saved) as { windows: WorkspaceWindow[]; focusedWindowId: string | null };
                setWindows(parsed.windows ?? []);
                setFocusedWindowId(parsed.focusedWindowId ?? null);
            }
        } catch {
            // ignore parse errors
        }
    }, []);

    useEffect(() => {
        if (localStorage.getItem(TUTORIAL_STORAGE_KEY)) return;
        const id = window.setTimeout(() => {
            analytics.trackAction("tabbar_tutorial.open", { data: { source: "first_run" } });
            setTutorialOpen(true);
        }, 650);
        return () => window.clearTimeout(id);
    }, [analytics]);

    // ── Persist workspace to localStorage ─────────────────────────────────────
    useEffect(() => {
        localStorage.setItem(WORKSPACE_STORAGE_KEY, JSON.stringify({ windows, focusedWindowId }));
    }, [windows, focusedWindowId]);

    useEffect(() => {
        api.listProviders().then((providers) => {
            const def = providers.find((p) => p.is_default) ?? null;
            setDefaultProvider(def);
        });
    }, []);

    useEffect(() => {
        if (workspaceMode) {
            analytics.setScreen("dashboard.workspace", { open_window_count: openWindowCount });
        }
    }, [analytics, openWindowCount, workspaceMode]);

    useEffect(() => {
        const onKey = (e: KeyboardEvent) => {
            if (!e.metaKey) return;
            if (e.key === "r") { e.preventDefault(); window.location.reload(); }
            if (e.key === "k") {
                e.preventDefault();
                analytics.trackAction("command_palette.open", { data: { source: "keyboard" } });
                setPaletteOpen(true);
            }
        };
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [analytics]);

    function handlePaletteSelect(panelType: PaletteNavType, id: string) {
        analytics.trackAction("command_palette.select", { data: { panel_type: panelType, target_id: id } });
        if (panelType === "chat") {
            setFocusId(id);
        } else {
            setContextPanel({ type: panelType, id });
        }
        setPaletteOpen(false);
    }

    function openContextPanel(type: ContextPanelState["type"], id?: string) {
        if (type) {
            analytics.trackAction(`panel.${type}.open`, { data: { panel_type: type, target_id: id } });
        }
        setContextPanel({ type, id });
    }

    function closeTutorial() {
        localStorage.setItem(TUTORIAL_STORAGE_KEY, "true");
        analytics.trackAction("tabbar_tutorial.close");
        setTutorialOpen(false);
    }

    // ── Open a URL in the workspace ────────────────────────────────────────────
    function openInWorkspace(url: string, title: string) {
        analytics.trackAction("workspace.open", { data: { url, title } });
        const now = Date.now();
        const existing = windows.find((w) => w.url === url);
        if (existing) {
            setWindows((prev) =>
                prev.map((w) => w.id === existing.id ? { ...w, minimized: false, focusedAt: now } : w)
            );
            setFocusedWindowId(existing.id);
        } else {
            const id = `w-${now}-${Math.random().toString(36).slice(2)}`;
            const newWindow: WorkspaceWindow = { id, title, url, minimized: false, focusedAt: now };
            setWindows((prev) => [...prev, newWindow]);
            setFocusedWindowId(id);
        }
        setWorkspaceMode(true);
    }

    function handleCloseWindow(id: string) {
        analytics.trackAction("workspace.window.close", { data: { window_id: id } });
        setWindows((prev) => {
            const remaining = prev.filter((w) => w.id !== id);
            if (focusedWindowId === id) {
                setFocusedWindowId(remaining[0]?.id ?? null);
            }
            return remaining;
        });
    }

    function handleMinimizeWindow(id: string) {
        analytics.trackAction("workspace.window.minimize", { data: { window_id: id } });
        setWindows((prev) => prev.map((w) => w.id === id ? { ...w, minimized: !w.minimized } : w));
        // If we just minimized the focused window, focus the next visible one
        setWindows((prev) => {
            const win = prev.find((w) => w.id === id);
            if (win?.minimized && focusedWindowId === id) {
                const next = prev.find((w) => w.id !== id && !w.minimized);
                setFocusedWindowId(next?.id ?? null);
            }
            return prev;
        });
    }

    return (
        <ThemeProvider theme={darkTheme}>
            <CssBaseline />
            <Box sx={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}>

                {/* ── Top app bar ──────────────────────────────────────────────────── */}
                <AppBar position="static" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, flexShrink: 0 }}>
                    <Toolbar variant="dense" sx={{ gap: 2, minHeight: 48 }}>
                        {/* Logo */}
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                            <SmartToyIcon sx={{ color: "primary.main", fontSize: 22 }} />
                            <Typography variant="subtitle1" fontWeight={700} letterSpacing={-0.3}>
                                VLoop Harness
                            </Typography>
                        </Box>

                        <Box sx={{ flexGrow: 1 }} />

                        {/* Provider status */}
                        {defaultProvider ? (
                            <Tooltip title={`Active: ${defaultProvider.name} — ${defaultProvider.model}`}>
                                <Chip
                                    icon={
                                        <FiberManualRecordIcon sx={{ fontSize: "10px !important", color: "#4ade80 !important" }} />
                                    }
                                    label={`${defaultProvider.name} · ${defaultProvider.model}`}
                                    size="small"
                                    variant="outlined"
                                    sx={{ borderColor: "rgba(74,222,128,0.4)", fontSize: "0.72rem", cursor: "default" }}
                                />
                            </Tooltip>
                        ) : (
                            <Chip
                                label="No provider"
                                size="small"
                                variant="outlined"
                                sx={{ borderColor: "warning.dark", color: "warning.main", fontSize: "0.72rem" }}
                            />
                        )}

                        {/* Connection status */}
                        <Chip
                            icon={
                                <FiberManualRecordIcon
                                    sx={{
                                        fontSize: "10px !important",
                                        color: `${connected ? "#4ade80" : "#f87171"} !important`,
                                    }}
                                />
                            }
                            label={connected ? "connected" : "disconnected"}
                            size="small"
                            variant="outlined"
                            sx={{
                                borderColor: connected ? "rgba(74,222,128,0.3)" : "rgba(248,113,113,0.3)",
                                fontSize: "0.72rem",
                                cursor: "default",
                            }}
                        />

                        {/* Search and tutorial */}
                        <Tooltip title="Search">
                            <IconButton
                                size="small"
                                onClick={() => {
                                    analytics.trackAction("command_palette.open", { data: { source: "app_bar" } });
                                    setPaletteOpen(true);
                                }}
                                sx={{ color: "text.secondary" }}
                            >
                                <SearchIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>

                        <Tooltip title="Show tab bar tour">
                            <IconButton
                                size="small"
                                onClick={() => {
                                    analytics.trackAction("tabbar_tutorial.open", { data: { source: "app_bar" } });
                                    setTutorialOpen(true);
                                }}
                                sx={{ color: "text.secondary" }}
                            >
                                <HelpOutlineIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>

                        {/* Channels toggle */}
                        <Tooltip title={currentView === "channels" ? "Exit Channels" : "Open Channels"}>
                            <IconButton
                                size="small"
                                onClick={() => {
                                    setCurrentView((v) => {
                                        const next = v === "channels" ? "chat" : "channels";
                                        if (next === "channels") setWorkspaceMode(false);
                                        return next;
                                    });
                                }}
                                sx={{ color: currentView === "channels" ? "primary.main" : "text.secondary" }}
                            >
                                <ForumIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>

                        {/* Workspace toggle */}
                        <Tooltip title={workspaceMode ? "Exit workspace" : "Open workspace"}>
                            <IconButton
                                size="small"
                                onClick={() => {
                                    const next = !workspaceMode;
                                    setWorkspaceMode(next);
                                    if (next) setCurrentView("chat");
                                }}
                                sx={{ color: workspaceMode ? "primary.main" : "text.secondary" }}
                            >
                                <Badge
                                    badgeContent={openWindowCount > 0 ? openWindowCount : undefined}
                                    color="primary"
                                    sx={{ "& .MuiBadge-badge": { fontSize: "0.6rem", minWidth: 14, height: 14 } }}
                                >
                                    <DashboardIcon fontSize="small" />
                                </Badge>
                            </IconButton>
                        </Tooltip>

                        {/* View registry */}
                        <Tooltip title="View Registry">
                            <IconButton
                                size="small"
                                onClick={() => {
                                    analytics.trackAction("view_registry.open", { data: { surface: "app_bar" } });
                                    setViewRegistryOpen(true);
                                }}
                                sx={{ color: "text.secondary" }}
                            >
                                <ViewListIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>

                        {/* Settings gear */}
                        <Tooltip title="Settings">
                            <IconButton
                                size="small"
                                onClick={() => {
                                    analytics.trackAction("settings.open", { data: { surface: "app_bar" } });
                                    setSettingsOpen(true);
                                }}
                                sx={{ color: "text.secondary" }}
                            >
                                <SettingsIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                    </Toolbar>
                </AppBar>

                {/* ── Main content ─────────────────────────────────────────────────── */}
                <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
                    {workspaceMode ? (
                        /* ── Workspace mode: split chat + iframe area ── */
                        <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>

                            {/* Collapsible chat sidebar */}
                            <Box sx={{ display: "flex", flexShrink: 0, position: "relative" }}>
                                <Box
                                    sx={{
                                        width: chatCollapsed ? 0 : 350,
                                        overflow: "hidden",
                                        transition: "width 0.2s ease",
                                        height: "100%",
                                    }}
                                >
                                    <Box sx={{ width: 350, height: "100%" }}>
                                        <ChatPanel
                                            focusSessionId={focusId}
                                            onFocused={() => setFocusId(null)}
                                            onOpenPanel={openContextPanel}
                                            onOpenWorkspace={openInWorkspace}
                                        />
                                    </Box>
                                </Box>

                                {/* Collapse / expand toggle */}
                                <Box
                                    sx={{
                                        position: "absolute",
                                        right: -16,
                                        top: "50%",
                                        transform: "translateY(-50%)",
                                        zIndex: 10,
                                    }}
                                >
                                    <Tooltip title={chatCollapsed ? "Expand chat" : "Collapse chat"}>
                                        <IconButton
                                            size="small"
                                            onClick={() => {
                                                analytics.trackAction("workspace.chat_sidebar.toggle", {
                                                    data: { next_collapsed: !chatCollapsed },
                                                });
                                                setChatCollapsed((v) => !v);
                                            }}
                                            sx={{
                                                bgcolor: "background.paper",
                                                border: "1px solid",
                                                borderColor: "divider",
                                                width: 24,
                                                height: 24,
                                                "&:hover": { bgcolor: "action.hover" },
                                            }}
                                        >
                                            {chatCollapsed
                                                ? <ChevronRightIcon sx={{ fontSize: 16 }} />
                                                : <ChevronLeftIcon sx={{ fontSize: 16 }} />
                                            }
                                        </IconButton>
                                    </Tooltip>
                                </Box>
                            </Box>

                            {/* Workspace area */}
                            <Box sx={{ flexGrow: 1, overflow: "hidden", minWidth: 0 }}>
                                <WorkspaceArea
                                    windows={windows}
                                    focusedId={focusedWindowId}
                                    onFocus={setFocusedWindowId}
                                    onClose={handleCloseWindow}
                                    onMinimize={handleMinimizeWindow}
                                    onOpenNew={openInWorkspace}
                                />
                            </Box>
                        </Box>
                    ) : (
                        /* ── Chat mode: full-width ChatPanel or ChannelsPanel ── */
                        currentView === "channels" ? (
                            <ChannelsPanel />
                        ) : (
                            <ChatPanel
                                focusSessionId={focusId}
                                onFocused={() => setFocusId(null)}
                                onOpenPanel={openContextPanel}
                                onOpenWorkspace={openInWorkspace}
                            />
                        )
                    )}
                </Box>
            </Box>

            {/* ── Settings container — Dialog (desktop) / bottom Drawer (mobile) ── */}
            {isMobile ? (
                <Drawer
                    anchor="bottom"
                    open={settingsOpen}
                    onClose={() => setSettingsOpen(false)}
                    PaperProps={{
                        sx: {
                            maxHeight: "80vh",
                            borderRadius: "12px 12px 0 0",
                            overflow: "auto",
                        },
                    }}
                >
                    {/* Drag handle indicator */}
                    <Box sx={{ display: "flex", justifyContent: "center", pt: 1, pb: 0.5, flexShrink: 0 }}>
                        <Box sx={{ width: 36, height: 4, borderRadius: 2, bgcolor: "divider" }} />
                    </Box>
                    <Box sx={{ display: "flex", alignItems: "center", px: 2, pt: 0.5, pb: 1, flexShrink: 0 }}>
                        <Typography variant="subtitle1" fontWeight={700} sx={{ flexGrow: 1 }}>
                            Settings
                        </Typography>
                        <Tooltip title="Close">
                            <IconButton size="small" onClick={() => setSettingsOpen(false)}>
                                ✕
                            </IconButton>
                        </Tooltip>
                    </Box>
                    <SettingsPanel />
                </Drawer>
            ) : (
                <Dialog
                    open={settingsOpen}
                    onClose={() => setSettingsOpen(false)}
                    maxWidth="sm"
                    fullWidth
                    scroll="paper"
                >
                    <DialogTitle sx={{ display: "flex", alignItems: "center" }}>
                        <SettingsIcon fontSize="small" sx={{ mr: 1, color: "text.secondary" }} />
                        Settings
                    </DialogTitle>
                    <DialogContent dividers sx={{ p: 0 }}>
                        <SettingsPanel />
                    </DialogContent>
                </Dialog>
            )}

            {/* ── Contextual right/bottom panel ────────────────────────────────── */}
            <ContextualPanel
                open={contextPanel.type !== null}
                panelType={contextPanel.type}
                panelId={contextPanel.id}
                onClose={() => setContextPanel({ type: null })}
            />

            {/* ── View Registry drawer ─────────────────────────────────────────── */}
            <Drawer
                anchor="right"
                open={viewRegistryOpen}
                onClose={() => setViewRegistryOpen(false)}
                PaperProps={{
                    sx: { width: 350, border: "none", borderLeft: "1px solid", borderColor: "divider" },
                }}
            >
                <ViewRegistry
                    onSelect={(item) => {
                        analytics.trackAction("view_registry.select", { data: { item_id: item.id, item_type: item.type } });
                        // TODO: Handle selection based on item type
                        setViewRegistryOpen(false);
                    }}
                    onClose={() => setViewRegistryOpen(false)}
                />
            </Drawer>

            {/* ── Cmd+K palette ────────────────────────────────────────────────── */}
            <CommandPalette
                open={paletteOpen}
                onClose={() => setPaletteOpen(false)}
                onSelect={handlePaletteSelect}
            />

            <TabbarTutorial open={tutorialOpen} onClose={closeTutorial} />
        </ThemeProvider>
    );
}
