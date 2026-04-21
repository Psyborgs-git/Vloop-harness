/**
 * CommandPalette — Cmd+K spotlight-style search.
 *
 * Loads all sessions, DSPy components, and pipelines on open then
 * filters them by query.  Arrow keys + Enter navigate; Escape closes.
 */

import SearchIcon from "@mui/icons-material/Search";
import {
  Box,
  Dialog,
  DialogContent,
  InputAdornment,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  ListSubheader,
  TextField,
  Typography,
} from "@mui/material";
import React, { useEffect, useRef, useState } from "react";

import * as api from "./api";
import type { ChatSession, ContextPanelType, DSPyComponent, Pipeline } from "./types";

export type PaletteNavType = "chat" | Exclude<ContextPanelType, null>;

interface PaletteItem {
  id: string;
  label: string;
  panelType: PaletteNavType;
  group: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSelect: (panelType: PaletteNavType, id: string) => void;
}

export default function CommandPalette({ open, onClose, onSelect }: Props) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<PaletteItem[]>([]);
  const [focusIdx, setFocusIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setFocusIdx(0);
    Promise.all([
      api.listSessions(),
      api.listComponents(),
      api.listPipelines(),
    ]).then(([sessions, comps, pipes]) => {
      setItems([
        ...(sessions as ChatSession[]).map((s) => ({
          id: s.id,
          label: s.title,
          panelType: "chat" as const,
          group: "Chat Sessions",
        })),
        ...(comps as DSPyComponent[]).map((c) => ({
          id: c.id,
          label: c.name,
          panelType: "dspy" as const,
          group: "DSPy Components",
        })),
        ...(pipes as Pipeline[]).map((p) => ({
          id: p.id,
          label: p.name,
          panelType: "pipelines" as const,
          group: "Pipelines",
        })),
      ]);
    });
  }, [open]);

  const filtered = query.trim()
    ? items.filter((i) => i.label.toLowerCase().includes(query.toLowerCase()))
    : items;

  const groups = Array.from(new Set(filtered.map((i) => i.group)));
  const flat = groups.flatMap((g) => filtered.filter((i) => i.group === g));

  function select(item: PaletteItem) {
    onSelect(item.panelType, item.id);
  }

  function handleKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setFocusIdx((p) => Math.min(p + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setFocusIdx((p) => Math.max(p - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flat[focusIdx]) select(flat[focusIdx]);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="sm"
      fullWidth
      PaperProps={{
        sx: { mt: "12vh", verticalAlign: "top", borderRadius: 2, overflow: "hidden" },
      }}
      TransitionProps={{ onEntered: () => inputRef.current?.focus() }}
    >
      <DialogContent sx={{ p: 0 }}>
        {/* Search input */}
        <TextField
          inputRef={inputRef}
          fullWidth
          placeholder="Search sessions, components, pipelines…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setFocusIdx(0);
          }}
          onKeyDown={handleKey}
          variant="outlined"
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon sx={{ color: "text.secondary", fontSize: 20 }} />
              </InputAdornment>
            ),
            sx: {
              borderRadius: 0,
              "& fieldset": { border: "none" },
              borderBottom: "1px solid",
              borderColor: "divider",
            },
          }}
          sx={{ px: 0 }}
        />

        {/* Results */}
        {flat.length === 0 ? (
          <Box sx={{ p: 3, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">
              No results
            </Typography>
          </Box>
        ) : (
          <List
            dense
            disablePadding
            sx={{ maxHeight: 360, overflowY: "auto" }}
            subheader={<li />}
          >
            {groups.map((group) => (
              <li key={group}>
                <ul style={{ padding: 0, margin: 0, listStyle: "none" }}>
                  <ListSubheader
                    sx={{
                      bgcolor: "background.paper",
                      lineHeight: "30px",
                      fontSize: "0.68rem",
                      letterSpacing: 1,
                      textTransform: "uppercase",
                      color: "text.disabled",
                    }}
                  >
                    {group}
                  </ListSubheader>
                  {flat
                    .filter((i) => i.group === group)
                    .map((item) => {
                      const idx = flat.indexOf(item);
                      return (
                        <ListItem key={item.id} disablePadding>
                          <ListItemButton
                            selected={focusIdx === idx}
                            onClick={() => select(item)}
                            onMouseEnter={() => setFocusIdx(idx)}
                            sx={{ py: 0.75, px: 2.5 }}
                          >
                            <ListItemText
                              primary={item.label}
                              primaryTypographyProps={{ variant: "body2" }}
                            />
                          </ListItemButton>
                        </ListItem>
                      );
                    })}
                </ul>
              </li>
            ))}
          </List>
        )}
      </DialogContent>
    </Dialog>
  );
}
