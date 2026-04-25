/**
 * WorkspaceArea — tabbed iframe workspace for embedded app views.
 *
 * Features:
 *  • Tab bar (one tab per window) with minimize + close buttons
 *  • "+" button to open a new URL via a small dialog
 *  • Minimized windows are excluded from the visible iframe area
 *  • Placeholder when no windows are open
 */

import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import MinimizeIcon from "@mui/icons-material/Minimize";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { type MouseEvent, useState } from "react";

import type { WorkspaceWindow } from "./types";

interface Props {
  windows: WorkspaceWindow[];
  focusedId: string | null;
  onFocus: (id: string) => void;
  onClose: (id: string) => void;
  onMinimize: (id: string) => void;
  onOpenNew: (url: string, title: string) => void;
}

/** Allow only safe relative paths and http/https URLs for iframe src. */
function sanitizeIframeSrc(url: string): string {
  if (url.startsWith("/") || url.startsWith("./") || url.startsWith("../")) {
    return url;
  }
  try {
    const parsed = new URL(url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      return url;
    }
  } catch {
    // not a valid absolute URL
  }
  return "about:blank";
}

export default function WorkspaceArea({
  windows,
  focusedId,
  onFocus,
  onClose,
  onMinimize,
  onOpenNew,
}: Props) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [newTitle, setNewTitle] = useState("");

  const visibleWindows = windows.filter((w) => !w.minimized);
  const focusedWindow =
    windows.find((w) => w.id === focusedId && !w.minimized) ??
    visibleWindows[0] ??
    null;

  function handleOpenNew() {
    if (!newUrl.trim()) return;
    onOpenNew(newUrl.trim(), newTitle.trim() || newUrl.trim());
    setNewUrl("");
    setNewTitle("");
    setDialogOpen(false);
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>

      {/* Tab bar */}
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
          flexShrink: 0,
        }}
      >
        <Tabs
          value={focusedWindow?.id ?? null}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ flexGrow: 1, minHeight: 40 }}
        >
          {windows.map((w) => (
            <Tab
              key={w.id}
              value={w.id}
              onClick={() => { if (!w.minimized) onFocus(w.id); }}
              sx={{ minHeight: 40, textTransform: "none", fontSize: "0.82rem", px: 1, py: 0 }}
              label={
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <Typography
                    component="span"
                    variant="inherit"
                    sx={{ opacity: w.minimized ? 0.5 : 1, fontSize: "inherit" }}
                  >
                    {w.minimized ? `[–] ${w.title}` : w.title}
                  </Typography>

                  {/* Minimize */}
                  <Box
                    component="span"
                    onClick={(e: MouseEvent<HTMLSpanElement>) => {
                      e.stopPropagation();
                      onMinimize(w.id);
                    }}
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      cursor: "pointer",
                      p: "2px",
                      borderRadius: "50%",
                      "&:hover": { bgcolor: "action.hover" },
                      opacity: 0.6,
                      "&:hover > *": { opacity: 1 },
                    }}
                  >
                    <MinimizeIcon sx={{ fontSize: 12 }} />
                  </Box>

                  {/* Close */}
                  <Box
                    component="span"
                    onClick={(e: MouseEvent<HTMLSpanElement>) => {
                      e.stopPropagation();
                      onClose(w.id);
                    }}
                    sx={{
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      cursor: "pointer",
                      p: "2px",
                      borderRadius: "50%",
                      "&:hover": { bgcolor: "action.hover" },
                      opacity: 0.6,
                    }}
                  >
                    <CloseIcon sx={{ fontSize: 12 }} />
                  </Box>
                </Box>
              }
            />
          ))}
        </Tabs>

        <Tooltip title="Open new app window">
          <Box
            component="span"
            onClick={() => setDialogOpen(true)}
            sx={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              p: "6px",
              mx: 0.5,
              borderRadius: 1,
              color: "text.secondary",
              "&:hover": { bgcolor: "action.hover", color: "text.primary" },
              flexShrink: 0,
            }}
          >
            <AddIcon fontSize="small" />
          </Box>
        </Tooltip>
      </Box>

      {/* Content area */}
      <Box sx={{ flexGrow: 1, overflow: "hidden", position: "relative" }}>
        {windows.length === 0 ? (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              flexDirection: "column",
              gap: 1,
              color: "text.secondary",
              p: 3,
              textAlign: "center",
            }}
          >
            <Typography variant="body2">No apps open.</Typography>
            <Typography variant="caption">
              Open a view from the Chat panel or Agent Runs.
            </Typography>
          </Box>
        ) : focusedWindow ? (
          <iframe
            key={focusedWindow.id}
            src={sanitizeIframeSrc(focusedWindow.url)}
            style={{ width: "100%", height: "100%", border: "none", display: "block" }}
            title={focusedWindow.title}
          />
        ) : (
          <Box
            sx={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              color: "text.secondary",
            }}
          >
            <Typography variant="body2">All windows are minimized.</Typography>
          </Box>
        )}
      </Box>

      {/* New window dialog */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Open App</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "12px !important" }}>
          <TextField
            label="URL"
            size="small"
            fullWidth
            value={newUrl}
            onChange={(e) => setNewUrl(e.target.value)}
            placeholder="/ui/MyApp"
            autoFocus
            onKeyDown={(e) => { if (e.key === "Enter" && newUrl.trim()) handleOpenNew(); }}
          />
          <TextField
            label="Label (optional)"
            size="small"
            fullWidth
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="My App"
            onKeyDown={(e) => { if (e.key === "Enter" && newUrl.trim()) handleOpenNew(); }}
          />
        </DialogContent>
        <DialogActions>
          <Button size="small" onClick={() => setDialogOpen(false)}>Cancel</Button>
          <Button size="small" variant="contained" onClick={handleOpenNew} disabled={!newUrl.trim()}>
            Open
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
