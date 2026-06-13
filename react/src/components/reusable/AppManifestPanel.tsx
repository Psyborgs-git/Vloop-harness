/**
 * AppManifestPanel — create, list, and manage full-stack app manifests.
 *
 * Features:
 *  • List of app manifests with status chips
 *  • Create new manifest form
 *  • Promote / archive status controls
 *  • Link to open in workspace
 */

import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  IconButton,
  List,
  ListItem,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";
import type { AppManifest } from "./types";

interface Props {
  focusManifestId?: string;
  onFocused?: () => void;
}

const STATUS_COLOR: Record<string, "default" | "warning" | "info" | "success" | "error"> = {
  draft: "default",
  validated: "info",
  active: "success",
  archived: "warning",
};

const NEXT_STATUS: Record<string, string> = {
  draft: "validated",
  validated: "active",
  active: "archived",
  archived: "draft",
};

export default function AppManifestPanel({ focusManifestId, onFocused }: Props) {
  const [manifests, setManifests] = useState<AppManifest[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);

  // New form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [backendType, setBackendType] = useState("pipeline");
  const [backendId, setBackendId] = useState("");
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listAppManifests();
      setManifests(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (focusManifestId) {
      onFocused?.();
    }
  }, [focusManifestId, onFocused]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      const m = await api.createAppManifest({
        name,
        description,
        backend_type: backendType as AppManifest["backend_type"],
        backend_id: backendId || undefined,
      });
      setManifests((prev) => [m, ...prev]);
      setShowNew(false);
      setName("");
      setDescription("");
      setBackendId("");
    } finally {
      setSaving(false);
    }
  };

  const handlePromote = async (manifest: AppManifest) => {
    const next = NEXT_STATUS[manifest.status] ?? "draft";
    const updated = await api.promoteAppManifest(manifest.id, next);
    setManifests((prev) => prev.map((m) => (m.id === updated.id ? updated : m)));
  };

  const handleDelete = async (id: string) => {
    await api.deleteAppManifest(id);
    setManifests((prev) => prev.filter((m) => m.id !== id));
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 1, flexShrink: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
          {manifests.length} manifest{manifests.length !== 1 ? "s" : ""}
        </Typography>
        <Tooltip title="Refresh">
          <IconButton size="small" onClick={load} disabled={loading}>
            {loading ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="New manifest">
          <IconButton size="small" onClick={() => setShowNew((v) => !v)}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* New manifest form */}
      <Collapse in={showNew} unmountOnExit>
        <Box sx={{ px: 1.5, pb: 1, display: "flex", flexDirection: "column", gap: 1 }}>
          <TextField
            label="Name"
            size="small"
            fullWidth
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <TextField
            label="Description"
            size="small"
            fullWidth
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Select
            size="small"
            fullWidth
            value={backendType}
            onChange={(e) => setBackendType(e.target.value)}
          >
            <MenuItem value="pipeline">Pipeline</MenuItem>
            <MenuItem value="component">Component</MenuItem>
            <MenuItem value="dspy_module">DSPy Module</MenuItem>
          </Select>
          <TextField
            label="Backend ID (optional)"
            size="small"
            fullWidth
            value={backendId}
            onChange={(e) => setBackendId(e.target.value)}
          />
          <Button
            variant="contained"
            size="small"
            disabled={!name.trim() || saving}
            onClick={handleCreate}
            startIcon={saving ? <CircularProgress size={14} color="inherit" /> : undefined}
          >
            Create
          </Button>
        </Box>
        <Divider />
      </Collapse>

      {/* Manifest list */}
      <Box sx={{ flexGrow: 1, overflowY: "auto" }}>
        {manifests.length === 0 && !loading && (
          <Typography variant="caption" color="text.secondary" sx={{ p: 2, display: "block" }}>
            No app manifests yet. Click + to create one.
          </Typography>
        )}
        <List dense disablePadding>
          {manifests.map((m) => (
            <ListItem
              key={m.id}
              disablePadding
              sx={{ px: 1.5, py: 0.75, borderBottom: "1px solid", borderColor: "divider" }}
            >
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap sx={{ fontSize: "0.82rem" }}>
                  {m.name}
                </Typography>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.25, flexWrap: "wrap" }}>
                  <Chip
                    label={m.status}
                    size="small"
                    color={STATUS_COLOR[m.status] ?? "default"}
                    sx={{ fontSize: "0.7rem", height: 18 }}
                  />
                  <Chip
                    label={m.backend_type}
                    size="small"
                    variant="outlined"
                    sx={{ fontSize: "0.7rem", height: 18 }}
                  />
                  <Typography variant="caption" color="text.secondary">
                    {m.react_views.length} view{m.react_views.length !== 1 ? "s" : ""}
                  </Typography>
                </Box>
              </Box>
              <Box sx={{ display: "flex", alignItems: "center" }}>
                {m.status === "active" && m.react_views.length > 0 && (
                  <Tooltip title="Open first view">
                    <IconButton
                      size="small"
                      component="a"
                      href={`/ui/${m.react_views[0]}`}
                      target="_blank"
                      rel="noopener"
                    >
                      <OpenInNewIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
                <Tooltip title={`Promote → ${NEXT_STATUS[m.status]}`}>
                  <Button
                    size="small"
                    sx={{ minWidth: 0, px: 0.5, fontSize: "0.7rem" }}
                    onClick={() => handlePromote(m)}
                  >
                    {NEXT_STATUS[m.status]}
                  </Button>
                </Tooltip>
                <Tooltip title="Delete">
                  <IconButton
                    size="small"
                    onClick={() => handleDelete(m.id)}
                    color="error"
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            </ListItem>
          ))}
        </List>
      </Box>
    </Box>
  );
}
