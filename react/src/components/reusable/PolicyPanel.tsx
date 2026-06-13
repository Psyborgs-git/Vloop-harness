/**
 * PolicyPanel — view and edit the tool execution policy.
 *
 * Displays the effective policy and allows editing the project-local policy
 * via a JSON editor.
 */

import SaveIcon from "@mui/icons-material/Save";
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  TextField,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";

import * as api from "./api";
import type { PolicyConfig } from "./types";

export default function PolicyPanel() {
  const [_policy, setPolicy] = useState<PolicyConfig | null>(null);
  const [raw, setRaw] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const cfg = await api.getPolicy();
      setPolicy(cfg);
      setRaw(JSON.stringify(cfg, null, 2));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function handleRawChange(value: string) {
    setRaw(value);
    setParseError(null);
    try {
      JSON.parse(value);
    } catch {
      setParseError("Invalid JSON");
    }
  }

  async function save() {
    if (parseError) return;
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const parsed = JSON.parse(raw) as PolicyConfig;
      const updated = await api.updatePolicy(parsed);
      setPolicy(updated);
      setRaw(JSON.stringify(updated, null, 2));
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
        <CircularProgress size={24} />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 2, height: "100%", overflow: "auto" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="subtitle2" fontWeight={600} sx={{ flexGrow: 1 }}>
          Tool Execution Policy
        </Typography>
        <Button
          size="small"
          variant="contained"
          startIcon={saving ? <CircularProgress size={14} color="inherit" /> : <SaveIcon />}
          onClick={save}
          disabled={saving || !!parseError}
        >
          Save
        </Button>
      </Box>

      <Typography variant="body2" color="text.secondary">
        This is the effective merged policy (global + project-local). Edits are saved to{" "}
        <code>.vloop/policy.json</code> in the workspace root. The permanent blocklist
        includes built-in entries that cannot be removed.
      </Typography>

      {error && (
        <Alert severity="error" variant="outlined" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" variant="outlined">
          Policy saved and reloaded successfully.
        </Alert>
      )}

      <TextField
        multiline
        fullWidth
        minRows={20}
        value={raw}
        onChange={(e) => handleRawChange(e.target.value)}
        error={!!parseError}
        helperText={parseError ?? "Edit the JSON policy configuration above"}
        inputProps={{ style: { fontFamily: "monospace", fontSize: "0.8rem" } }}
      />
    </Box>
  );
}
