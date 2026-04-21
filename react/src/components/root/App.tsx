/**
 * VLoop Harness — Root Dashboard (Chat-First)
 *
 * Layout:
 *  ┌─ TopBar ─────────────────────────────────────────────────────────┐
 *  │  VLoop Harness    [provider status]  [connection]  [⚙ settings]  │
 *  ├─ Main (full width) ──────────────────────────────────────────────┤
 *  │  ChatPanel (session sidebar + conversation)                       │
 *  └──────────────────────────────────────────────────────────────────┘
 *
 *  Settings opens as a Dialog (desktop) or bottom Drawer ≤80vh (mobile).
 *  DSPy / Pipelines / Tools open as a contextual right Drawer from chat actions.
 */

import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import SettingsIcon from "@mui/icons-material/Settings";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import {
  AppBar,
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
import ChatPanel from "./ChatPanel";
import CommandPalette from "./CommandPalette";
import type { PaletteNavType } from "./CommandPalette";
import ContextualPanel from "./ContextualPanel";
import SettingsPanel from "./SettingsPanel";
import type { ContextPanelState, Provider } from "./types";

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

export default function App() {
  const { connected } = useHarness();
  const [defaultProvider, setDefaultProvider] = useState<Provider | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [contextPanel, setContextPanel] = useState<ContextPanelState>({ type: null });

  const isMobile = useMediaQuery(darkTheme.breakpoints.down("md"));

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

  function handlePaletteSelect(panelType: PaletteNavType, id: string) {
    if (panelType === "chat") {
      setFocusId(id);
    } else {
      setContextPanel({ type: panelType, id });
    }
    setPaletteOpen(false);
  }

  function openContextPanel(type: ContextPanelState["type"], id?: string) {
    setContextPanel({ type, id });
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

            {/* Settings gear */}
            <Tooltip title="Settings">
              <IconButton size="small" onClick={() => setSettingsOpen(true)} sx={{ color: "text.secondary" }}>
                <SettingsIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Toolbar>
        </AppBar>

        {/* ── Main content (chat always full-width) ────────────────────────── */}
        <Box sx={{ flexGrow: 1, overflow: "hidden" }}>
          <ChatPanel
            focusSessionId={focusId}
            onFocused={() => setFocusId(null)}
            onOpenPanel={openContextPanel}
          />
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

      {/* ── Cmd+K palette ────────────────────────────────────────────────── */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onSelect={handlePaletteSelect}
      />
    </ThemeProvider>
  );
}

