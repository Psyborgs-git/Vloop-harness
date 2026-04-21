/**
 * VLoop Harness — Root Dashboard
 *
 * A modern AI-app dashboard built with Material UI dark theme.
 *
 * Layout:
 *  ┌─ TopBar ──────────────────────────────────────────────────────┐
 *  │  VLoop Harness    [provider status]  [connection]             │
 *  ├─ Sidebar ─┬─ Content ──────────────────────────────────────────┤
 *  │  Chat     │  <active panel>                                    │
 *  │  DSPy     │                                                    │
 *  │  Pipelines│                                                    │
 *  │  Settings │                                                    │
 *  └───────────┴────────────────────────────────────────────────────┘
 */

import AccountTreeIcon from "@mui/icons-material/AccountTree";
import ChatIcon from "@mui/icons-material/Chat";
import CodeIcon from "@mui/icons-material/Code";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import SettingsIcon from "@mui/icons-material/Settings";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import TerminalIcon from "@mui/icons-material/Terminal";
import {
  AppBar,
  Box,
  Chip,
  CssBaseline,
  Drawer,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  ThemeProvider,
  Toolbar,
  Tooltip,
  Typography,
  createTheme,
} from "@mui/material";
import React, { useEffect, useState } from "react";

import { useHarness } from "@harness/useHarness";
import * as api from "./api";
import ChatPanel from "./ChatPanel";
import CommandPalette from "./CommandPalette";
import DSPyPanel from "./DSPyPanel";
import PipelinePanel from "./PipelinePanel";
import SettingsPanel from "./SettingsPanel";
import ToolsPanel from "./ToolsPanel";
import type { NavTab, Provider } from "./types";

// ── MUI dark theme ────────────────────────────────────────────────────────────

const darkTheme = createTheme({
  palette: {
    mode: "dark",
    primary: {
      main: "#6366f1",       // indigo-500
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

// ── Sidebar navigation ────────────────────────────────────────────────────────

const SIDEBAR_WIDTH = 200;

const NAV_ITEMS: Array<{ tab: NavTab; label: string; icon: React.ReactNode }> = [
  { tab: "chat", label: "Chat", icon: <ChatIcon fontSize="small" /> },
  { tab: "dspy", label: "DSPy Components", icon: <CodeIcon fontSize="small" /> },
  { tab: "pipelines", label: "Pipelines", icon: <AccountTreeIcon fontSize="small" /> },
  { tab: "tools", label: "Tools", icon: <TerminalIcon fontSize="small" /> },
  { tab: "settings", label: "Settings", icon: <SettingsIcon fontSize="small" /> },
];

// ── Root app ──────────────────────────────────────────────────────────────────

export default function App() {
  const { connected } = useHarness();
  const [activeTab, setActiveTab] = useState<NavTab>("chat");
  const [defaultProvider, setDefaultProvider] = useState<Provider | null>(null);

  const [paletteOpen, setPaletteOpen] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);

  useEffect(() => {
    api.listProviders().then((providers) => {
      const def = providers.find((p) => p.is_default) ?? null;
      setDefaultProvider(def);
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.metaKey) return;
      if (e.key === "r") { e.preventDefault(); window.location.reload(); }
      if (e.key === "k") { e.preventDefault(); setPaletteOpen(true); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function handlePaletteSelect(tab: NavTab, id: string) {
    setFocusId(id);
    setActiveTab(tab);
    setPaletteOpen(false);
  }

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <Box sx={{ display: "flex", height: "100vh", overflow: "hidden" }}>

        {/* ── Top app bar ─────────────────────────────────────────────────── */}
        <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1 }}>
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
          </Toolbar>
        </AppBar>

        {/* ── Sidebar ─────────────────────────────────────────────────────── */}
        <Drawer
          variant="permanent"
          sx={{
            width: SIDEBAR_WIDTH,
            flexShrink: 0,
            "& .MuiDrawer-paper": { width: SIDEBAR_WIDTH, boxSizing: "border-box" },
          }}
        >
          <Toolbar variant="dense" sx={{ minHeight: 48 }} /> {/* offset for AppBar */}
          <Box sx={{ pt: 1 }}>
            <List dense disablePadding>
              {NAV_ITEMS.map(({ tab, label, icon }) => (
                <ListItem key={tab} disablePadding>
                  <ListItemButton
                    selected={activeTab === tab}
                    onClick={() => setActiveTab(tab)}
                  >
                    <ListItemIcon
                      sx={{
                        minWidth: 32,
                        color: activeTab === tab ? "primary.light" : "text.secondary",
                      }}
                    >
                      {icon}
                    </ListItemIcon>
                    <ListItemText
                      primary={label}
                      primaryTypographyProps={{
                        variant: "body2",
                        fontWeight: activeTab === tab ? 600 : 400,
                        color: activeTab === tab ? "primary.light" : "text.primary",
                      }}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          </Box>
        </Drawer>

        {/* ── Main content ─────────────────────────────────────────────────── */}
        <Box
          component="main"
          sx={{
            flexGrow: 1,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
            mt: "48px", // AppBar height
          }}
        >
          <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
            {activeTab === "chat" && (
              <ChatPanel
                onComponentSaved={() => {}}
                onNavigate={(tab) => setActiveTab(tab as NavTab)}
                focusSessionId={focusId}
                onFocused={() => setFocusId(null)}
              />
            )}
            {activeTab === "dspy" && (
              <DSPyPanel
                focusComponentId={focusId}
                onFocused={() => setFocusId(null)}
              />
            )}
            {activeTab === "pipelines" && (
              <PipelinePanel
                focusPipelineId={focusId}
                onFocused={() => setFocusId(null)}
              />
            )}
            {activeTab === "tools" && <ToolsPanel />}
            {activeTab === "settings" && (
              <Box sx={{ height: "100%", overflow: "auto" }}>
                <SettingsPanel />
              </Box>
            )}
          </Box>
        </Box>
      </Box>

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={handlePaletteSelect}
      />
    </ThemeProvider>
  );
}
