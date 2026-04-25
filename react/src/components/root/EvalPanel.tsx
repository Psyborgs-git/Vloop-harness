/**
 * EvalPanel — evaluation datasets and versioning for a DSPy component.
 *
 * Features:
 *  - List eval datasets, create/delete them
 *  - Run evaluation against a dataset → show pass/fail results
 *  - List component version snapshots
 *  - Create manual snapshot, rollback to a previous version
 */

import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import HistoryIcon from "@mui/icons-material/History";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
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
  ListItemText,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";
import type { ComponentVersion, EvalDataset, EvalResult } from "./api";

interface Props {
  componentId?: string;
}

const SX_COMPACT: React.CSSProperties = { fontSize: "0.82rem" };

export default function EvalPanel({ componentId }: Props) {
  if (!componentId) {
    return (
      <Box sx={{ p: 2 }}>
        <Typography variant="body2" color="text.secondary" sx={SX_COMPACT}>
          Select a DSPy component to view eval datasets.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "auto" }}>
      <EvalDatasetsSection componentId={componentId} />
      <Divider sx={{ my: 1 }} />
      <SnapshotsSection componentId={componentId} />
    </Box>
  );
}

// ── Eval Datasets ─────────────────────────────────────────────────────────────

function EvalDatasetsSection({ componentId }: { componentId: string }) {
  const [datasets, setDatasets] = useState<EvalDataset[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [results, setResults] = useState<Record<string, EvalResult | string>>({});
  const [running, setRunning] = useState<Record<string, boolean>>({});

  // New dataset form state
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newExamples, setNewExamples] = useState("");
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, [componentId]);

  async function load() {
    setLoading(true);
    try {
      setDatasets(await api.listEvalDatasets(componentId));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    setFormError(null);
    let examples: unknown[] | undefined;
    if (newExamples.trim()) {
      try {
        examples = JSON.parse(newExamples);
        if (!Array.isArray(examples)) throw new Error("Must be a JSON array");
      } catch (e: any) {
        setFormError(e.message);
        return;
      }
    }
    setSaving(true);
    try {
      await api.createEvalDataset(componentId, {
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        examples,
      });
      setNewName("");
      setNewDesc("");
      setNewExamples("");
      setShowForm(false);
      await load();
    } catch (e: any) {
      setFormError(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(datasetId: string) {
    await api.deleteEvalDataset(componentId, datasetId);
    setResults((r) => { const n = { ...r }; delete n[datasetId]; return n; });
    await load();
  }

  async function handleRun(datasetId: string) {
    setRunning((r) => ({ ...r, [datasetId]: true }));
    setResults((r) => ({ ...r, [datasetId]: "running" }));
    try {
      const res = await api.evaluateComponent(componentId, datasetId);
      setResults((r) => ({ ...r, [datasetId]: res }));
    } catch (e: any) {
      setResults((r) => ({ ...r, [datasetId]: `Error: ${e.message}` }));
    } finally {
      setRunning((r) => ({ ...r, [datasetId]: false }));
    }
  }

  return (
    <Box sx={{ p: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        <Typography variant="subtitle2" fontWeight={600} sx={{ flexGrow: 1, ...SX_COMPACT }}>
          Eval Datasets
        </Typography>
        <Tooltip title="New dataset">
          <IconButton size="small" onClick={() => setShowForm((v) => !v)}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Inline new dataset form */}
      <Collapse in={showForm}>
        <Box
          sx={{
            display: "flex",
            flexDirection: "column",
            gap: 1,
            mb: 1.5,
            p: 1.5,
            border: "1px solid",
            borderColor: "divider",
            borderRadius: 1,
          }}
        >
          <TextField
            label="Name *"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            size="small"
            fullWidth
            inputProps={{ style: SX_COMPACT }}
          />
          <TextField
            label="Description"
            value={newDesc}
            onChange={(e) => setNewDesc(e.target.value)}
            size="small"
            fullWidth
            inputProps={{ style: SX_COMPACT }}
          />
          <TextField
            label="Examples (JSON array)"
            value={newExamples}
            onChange={(e) => setNewExamples(e.target.value)}
            size="small"
            fullWidth
            multiline
            minRows={3}
            placeholder='[{"inputs": {}, "expected_outputs": {}}]'
            inputProps={{ style: { ...SX_COMPACT, fontFamily: "monospace" } }}
          />
          {formError && (
            <Typography variant="caption" color="error">
              {formError}
            </Typography>
          )}
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              size="small"
              variant="contained"
              onClick={handleCreate}
              disabled={!newName.trim() || saving}
              sx={{ fontSize: "0.75rem" }}
            >
              {saving ? "Saving…" : "Save"}
            </Button>
            <Button
              size="small"
              onClick={() => { setShowForm(false); setFormError(null); }}
              sx={{ fontSize: "0.75rem" }}
            >
              Cancel
            </Button>
          </Box>
        </Box>
      </Collapse>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
          <CircularProgress size={20} />
        </Box>
      ) : datasets.length === 0 ? (
        <Typography variant="caption" color="text.disabled">
          No eval datasets yet.
        </Typography>
      ) : (
        <List dense disablePadding>
          {datasets.map((ds) => {
            const res = results[ds.id];
            const isRunning = running[ds.id];
            return (
              <ListItem
                key={ds.id}
                disablePadding
                sx={{ flexDirection: "column", alignItems: "stretch", mb: 0.5 }}
              >
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <ListItemText
                    primary={ds.name}
                    secondary={ds.description || `${ds.examples?.length ?? 0} examples`}
                    primaryTypographyProps={{ variant: "body2", sx: { fontSize: "0.82rem" } }}
                    secondaryTypographyProps={{ variant: "caption" }}
                  />
                  <Tooltip title="Run eval">
                    <span>
                      <IconButton
                        size="small"
                        onClick={() => handleRun(ds.id)}
                        disabled={isRunning}
                        color="primary"
                      >
                        {isRunning ? (
                          <CircularProgress size={14} />
                        ) : (
                          <PlayArrowIcon fontSize="small" />
                        )}
                      </IconButton>
                    </span>
                  </Tooltip>
                  <Tooltip title="Delete dataset">
                    <IconButton
                      size="small"
                      onClick={() => handleDelete(ds.id)}
                      sx={{ opacity: 0.5, "&:hover": { opacity: 1, color: "error.main" } }}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
                {res && typeof res === "object" && (
                  <Chip
                    label={`${res.passed}/${res.total} passed`}
                    size="small"
                    color={res.passed === res.total ? "success" : "warning"}
                    sx={{ alignSelf: "flex-start", fontSize: "0.72rem", mb: 0.5 }}
                  />
                )}
                {res && typeof res === "string" && res !== "running" && (
                  <Typography variant="caption" color="error">
                    {res}
                  </Typography>
                )}
              </ListItem>
            );
          })}
        </List>
      )}
    </Box>
  );
}

// ── Snapshots / Versions ──────────────────────────────────────────────────────

function SnapshotsSection({ componentId }: { componentId: string }) {
  const [versions, setVersions] = useState<ComponentVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [snapshotting, setSnapshotting] = useState(false);

  useEffect(() => {
    load();
  }, [componentId]);

  async function load() {
    setLoading(true);
    try {
      setVersions(await api.listComponentVersions(componentId));
    } finally {
      setLoading(false);
    }
  }

  async function handleSnapshot() {
    setSnapshotting(true);
    try {
      await api.snapshotComponent(componentId, "Manual snapshot");
      await load();
    } finally {
      setSnapshotting(false);
    }
  }

  async function handleRollback(versionId: string, versionNumber: number) {
    if (!window.confirm(`Roll back to version ${versionNumber}? This will overwrite the current component.`)) return;
    await api.rollbackComponent(componentId, versionId);
    await load();
  }

  return (
    <Box sx={{ p: 1.5 }}>
      <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
        <HistoryIcon sx={{ fontSize: 15, mr: 0.5, color: "text.secondary" }} />
        <Typography variant="subtitle2" fontWeight={600} sx={{ flexGrow: 1, ...SX_COMPACT }}>
          Snapshots
        </Typography>
        <Button
          size="small"
          variant="outlined"
          onClick={handleSnapshot}
          disabled={snapshotting}
          sx={{ fontSize: "0.72rem", py: 0.25 }}
        >
          {snapshotting ? "Saving…" : "Snapshot"}
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 2 }}>
          <CircularProgress size={20} />
        </Box>
      ) : versions.length === 0 ? (
        <Typography variant="caption" color="text.disabled">
          No snapshots yet.
        </Typography>
      ) : (
        <List dense disablePadding>
          {versions.map((v) => (
            <ListItem
              key={v.id}
              disablePadding
              secondaryAction={
                <Tooltip title={`Rollback to v${v.version_number}`}>
                  <Button
                    size="small"
                    onClick={() => handleRollback(v.id, v.version_number)}
                    sx={{ fontSize: "0.72rem", minWidth: 0, py: 0.25 }}
                  >
                    Rollback
                  </Button>
                </Tooltip>
              }
            >
              <ListItemText
                primary={`v${v.version_number}${v.change_summary ? ` — ${v.change_summary}` : ""}`}
                secondary={new Date(v.created_at).toLocaleString()}
                primaryTypographyProps={{ variant: "body2", sx: { fontSize: "0.82rem" } }}
                secondaryTypographyProps={{ variant: "caption" }}
              />
            </ListItem>
          ))}
        </List>
      )}
    </Box>
  );
}
