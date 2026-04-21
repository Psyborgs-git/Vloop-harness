/**
 * DSPyPanel — browse, create, and run DSPy component definitions.
 *
 * Layout:
 *  Left: scrollable list of component cards
 *  Right: detail panel — code viewer + interactive runner
 */

import AddIcon from "@mui/icons-material/Add";
import CodeIcon from "@mui/icons-material/Code";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import React, { useEffect, useState } from "react";

import * as api from "./api";
import type { DSPyComponent, RunResult } from "./types";

const COMPONENT_TEMPLATE = `import dspy


class MyTaskSignature(dspy.Signature):
    """Describe what this component does."""
    input_text: str = dspy.InputField(desc="The input text")
    output_text: str = dspy.OutputField(desc="The output text")


class MyTask(dspy.Module):
    def __init__(self):
        self.predict = dspy.ChainOfThought(MyTaskSignature)

    def forward(self, input_text: str) -> dspy.Prediction:
        return self.predict(input_text=input_text)
`;

interface Props {
  focusComponentId?: string | null;
  onFocused?: () => void;
}

export default function DSPyPanel({ focusComponentId, onFocused }: Props) {
  const [components, setComponents] = useState<DSPyComponent[]>([]);
  const [selected, setSelected] = useState<DSPyComponent | null>(null);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [runInputs, setRunInputs] = useState<Record<string, string>>({});
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    refresh();
  }, []);

  // ── Jump to component from command palette ────────────────────────────────

  useEffect(() => {
    if (!focusComponentId || components.length === 0) return;
    const target = components.find((c) => c.id === focusComponentId);
    if (target) {
      setSelected(target);
      onFocused?.();
    }
  }, [focusComponentId, components]);

  async function refresh() {
    setLoading(true);
    try {
      const comps = await api.listComponents();
      setComponents(comps);
      if (selected) {
        const updated = comps.find((c) => c.id === selected.id);
        if (updated) setSelected(updated);
      }
    } finally {
      setLoading(false);
    }
  }

  async function remove(id: string) {
    await api.deleteComponent(id);
    if (selected?.id === id) setSelected(null);
    await refresh();
  }

  async function run() {
    if (!selected) return;
    setRunning(true);
    setRunResult(null);
    setRunError(null);
    try {
      const result = await api.runComponent(selected.id, runInputs);
      setRunResult(result);
    } catch (e: any) {
      setRunError(e.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Component list */}
      <Box
        sx={{
          width: 260,
          flexShrink: 0,
          borderRight: "1px solid",
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box sx={{ p: 1.5, display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="subtitle2" sx={{ flexGrow: 1, fontWeight: 600 }}>
            Components
          </Typography>
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={refresh}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="New component">
            <IconButton size="small" color="primary" onClick={() => setCreateOpen(true)}>
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Divider />
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", p: 3 }}>
            <CircularProgress size={24} />
          </Box>
        ) : (
          <List dense sx={{ overflow: "auto", flexGrow: 1 }}>
            {components.map((c) => (
              <ListItem
                key={c.id}
                disablePadding
                secondaryAction={
                  <IconButton
                    size="small"
                    onClick={() => remove(c.id)}
                    sx={{ opacity: 0.5, "&:hover": { opacity: 1, color: "error.main" } }}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                }
              >
                <ListItemButton
                  selected={selected?.id === c.id}
                  onClick={() => {
                    setSelected(c);
                    setRunResult(null);
                    setRunError(null);
                    const defaults: Record<string, string> = {};
                    c.signature_fields.inputs.forEach((f) => {
                      defaults[f.name] = "";
                    });
                    setRunInputs(defaults);
                  }}
                  sx={{ borderRadius: 1, mx: 0.5 }}
                >
                  <ListItemText
                    primary={c.name}
                    secondary={c.module_type}
                    primaryTypographyProps={{ variant: "body2", noWrap: true }}
                    secondaryTypographyProps={{ variant: "caption" }}
                  />
                </ListItemButton>
              </ListItem>
            ))}
            {components.length === 0 && (
              <ListItem>
                <ListItemText
                  primary="No components yet"
                  secondary="Ask the AI to create one, or click +"
                  primaryTypographyProps={{ variant: "caption", color: "text.secondary" }}
                  secondaryTypographyProps={{ variant: "caption", color: "text.disabled" }}
                />
              </ListItem>
            )}
          </List>
        )}
      </Box>

      {/* Detail panel */}
      <Box sx={{ flexGrow: 1, overflow: "auto", p: 2 }}>
        {selected ? (
          <ComponentDetail
            component={selected}
            runInputs={runInputs}
            setRunInputs={setRunInputs}
            onRun={run}
            running={running}
            runResult={runResult}
            runError={runError}
          />
        ) : (
          <Box sx={{ textAlign: "center", mt: 8, color: "text.secondary" }}>
            <CodeIcon sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
            <Typography variant="body2">Select a component to view details and run it</Typography>
          </Box>
        )}
      </Box>

      {/* Create dialog */}
      <CreateDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={(c) => {
          refresh();
          setSelected(c);
          setCreateOpen(false);
        }}
      />
    </Box>
  );
}

// ── Component detail ──────────────────────────────────────────────────────────

function ComponentDetail({
  component,
  runInputs,
  setRunInputs,
  onRun,
  running,
  runResult,
  runError,
}: {
  component: DSPyComponent;
  runInputs: Record<string, string>;
  setRunInputs: (v: Record<string, string>) => void;
  onRun: () => void;
  running: boolean;
  runResult: RunResult | null;
  runError: string | null;
}) {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      {/* Header */}
      <Box>
        <Typography variant="h6" fontWeight={600}>
          {component.name}
        </Typography>
        {component.description && (
          <Typography variant="body2" color="text.secondary">
            {component.description}
          </Typography>
        )}
        <Box sx={{ mt: 1, display: "flex", gap: 1 }}>
          <Chip label={component.module_type} size="small" color="primary" variant="outlined" />
          <Chip
            label={component.is_active ? "active" : "inactive"}
            size="small"
            color={component.is_active ? "success" : "default"}
            variant="outlined"
          />
        </Box>
      </Box>

      {/* Signature fields */}
      {(component.signature_fields.inputs.length > 0 ||
        component.signature_fields.outputs.length > 0) && (
        <Box>
          <Typography variant="subtitle2" gutterBottom fontWeight={600}>
            Signature
          </Typography>
          <Box sx={{ display: "flex", gap: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">
                INPUTS
              </Typography>
              {component.signature_fields.inputs.map((f) => (
                <Typography key={f.name} variant="body2">
                  <strong>{f.name}</strong>
                  {f.desc && ` — ${f.desc}`}
                </Typography>
              ))}
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">
                OUTPUTS
              </Typography>
              {component.signature_fields.outputs.map((f) => (
                <Typography key={f.name} variant="body2">
                  <strong>{f.name}</strong>
                  {f.desc && ` — ${f.desc}`}
                </Typography>
              ))}
            </Box>
          </Box>
        </Box>
      )}

      {/* Code viewer */}
      <Box>
        <Typography variant="subtitle2" gutterBottom fontWeight={600}>
          Source code
        </Typography>
        <SyntaxHighlighter
          language="python"
          style={vscDarkPlus as any}
          customStyle={{ borderRadius: 6, fontSize: "0.8rem", margin: 0 }}
        >
          {component.code}
        </SyntaxHighlighter>
      </Box>

      {/* Runner */}
      <Box>
        <Typography variant="subtitle2" gutterBottom fontWeight={600}>
          Run component
        </Typography>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          {component.signature_fields.inputs.map((f) => (
            <TextField
              key={f.name}
              label={f.name}
              helperText={f.desc}
              value={runInputs[f.name] ?? ""}
              onChange={(e) =>
                setRunInputs({ ...runInputs, [f.name]: e.target.value })
              }
              multiline
              minRows={2}
              size="small"
              fullWidth
            />
          ))}
          <Button
            variant="contained"
            startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
            onClick={onRun}
            disabled={running}
            sx={{ alignSelf: "flex-start" }}
          >
            {running ? "Running…" : "Run"}
          </Button>

          {runError && (
            <Alert severity="error" variant="outlined">
              {runError}
            </Alert>
          )}

          {runResult && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Output
              </Typography>
              {Object.entries(runResult.outputs).map(([k, v]) => (
                <Box key={k} sx={{ mb: 1 }}>
                  <Typography variant="caption" color="text.secondary">
                    {k}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      p: 1,
                      bgcolor: "background.default",
                      borderRadius: 1,
                      border: "1px solid",
                      borderColor: "divider",
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {String(v)}
                  </Typography>
                </Box>
              ))}
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// ── Create dialog ─────────────────────────────────────────────────────────────

function CreateDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (c: DSPyComponent) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [code, setCode] = useState(COMPONENT_TEMPLATE);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const comp = await api.createComponent({ name, description, code });
      onCreated(comp);
      setName("");
      setDescription("");
      setCode(COMPONENT_TEMPLATE);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>New DSPy Component</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <TextField
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          fullWidth
          size="small"
        />
        <TextField
          label="Python code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          multiline
          minRows={16}
          fullWidth
          size="small"
          inputProps={{ style: { fontFamily: "monospace", fontSize: "0.82rem" } }}
        />
        {error && (
          <Alert severity="error" variant="outlined">
            {error}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={save}
          disabled={!name.trim() || !code.trim() || saving}
        >
          {saving ? "Saving…" : "Save Component"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
