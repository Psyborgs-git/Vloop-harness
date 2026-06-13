/**
 * GenerateViewDialog — prompts user for a description/spec and triggers
 * AI generation of a React TSX view stub via POST /api/views/generate.
 */

import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";
import type { GeneratedView } from "./types";

interface Props {
  open: boolean;
  sessionId: string | null;
  onClose: () => void;
  onGenerated: (view: GeneratedView) => void;
}

export default function GenerateViewDialog({
  open,
  sessionId,
  onClose,
  onGenerated,
}: Props) {
  const [description, setDescription] = useState("");
  const [componentName, setComponentName] = useState("");
  const [spec, setSpec] = useState("");
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setDescription("");
      setComponentName("");
      setSpec("");
      setError(null);
    }
  }, [open]);

  async function generate() {
    if (!description.trim()) return;
    setGenerating(true);
    setError(null);
    try {
      const view = await api.generateView({
        description: description.trim(),
        component_name: componentName.trim() || undefined,
        spec: spec.trim() || undefined,
        session_id: sessionId ?? undefined,
      });
      onGenerated(view);
      onClose();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Generate React View Stub</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <TextField
          label="Describe the view"
          placeholder="e.g. A dashboard showing live metric cards with a refresh button"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          multiline
          minRows={3}
          fullWidth
          size="small"
          required
        />
        <TextField
          label="Component name (optional)"
          placeholder="e.g. MetricsDashboard"
          helperText="PascalCase — leave blank to let the AI pick"
          value={componentName}
          onChange={(e) => setComponentName(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label="Additional spec / constraints (optional)"
          placeholder="e.g. Must use MUI DataGrid, show last 24 h of data"
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
          multiline
          minRows={2}
          fullWidth
          size="small"
        />
        {error && (
          <Alert severity="error" variant="outlined">
            {error}
          </Alert>
        )}
        {generating && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <CircularProgress size={16} />
            <span style={{ fontSize: "0.82rem" }}>Generating…</span>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={generating}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={generate}
          disabled={!description.trim() || generating}
        >
          {generating ? "Generating…" : "Generate"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
