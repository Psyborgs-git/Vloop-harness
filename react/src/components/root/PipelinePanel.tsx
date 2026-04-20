/**
 * PipelinePanel — compose and execute DSPy component pipelines.
 *
 * Layout:
 *  Left: pipeline list
 *  Right: step editor + runner
 */

import AddIcon from "@mui/icons-material/Add";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import ArrowDownwardIcon from "@mui/icons-material/ArrowDownward";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Select,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import React, { useEffect, useState } from "react";

import * as api from "./api";
import type { DSPyComponent, Pipeline, PipelineStep, RunResult } from "./types";

export default function PipelinePanel() {
  const [pipelines, setPipelines] = useState<Pipeline[]>([]);
  const [components, setComponents] = useState<DSPyComponent[]>([]);
  const [selected, setSelected] = useState<Pipeline | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setLoading(true);
    try {
      const [pipes, comps] = await Promise.all([api.listPipelines(), api.listComponents()]);
      setPipelines(pipes);
      setComponents(comps);
    } finally {
      setLoading(false);
    }
  }

  async function createPipeline() {
    if (!newName.trim()) return;
    const p = await api.createPipeline({ name: newName, steps: [] });
    setNewName("");
    setCreating(false);
    await refresh();
    setSelected(p);
  }

  async function removePipeline(id: string) {
    await api.deletePipeline(id);
    if (selected?.id === id) setSelected(null);
    await refresh();
  }

  async function updateSteps(steps: PipelineStep[]) {
    if (!selected) return;
    const updated = await api.updatePipeline(selected.id, { steps });
    setSelected(updated);
    await refresh();
  }

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Pipeline list */}
      <Box
        sx={{
          width: 240,
          flexShrink: 0,
          borderRight: "1px solid",
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <Box sx={{ p: 1.5, display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="subtitle2" sx={{ flexGrow: 1, fontWeight: 600 }}>
            Pipelines
          </Typography>
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={refresh}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="New pipeline">
            <IconButton size="small" color="primary" onClick={() => setCreating(true)}>
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>

        {creating && (
          <Box sx={{ px: 1.5, pb: 1, display: "flex", gap: 0.5 }}>
            <TextField
              size="small"
              placeholder="Pipeline name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createPipeline()}
              fullWidth
              autoFocus
            />
            <Button size="small" variant="contained" onClick={createPipeline}>
              OK
            </Button>
          </Box>
        )}

        <Divider />
        <List dense sx={{ overflow: "auto", flexGrow: 1 }}>
          {loading ? (
            <Box sx={{ display: "flex", justifyContent: "center", p: 3 }}>
              <CircularProgress size={24} />
            </Box>
          ) : (
            pipelines.map((p) => (
              <ListItem
                key={p.id}
                disablePadding
                secondaryAction={
                  <IconButton
                    size="small"
                    onClick={() => removePipeline(p.id)}
                    sx={{ opacity: 0.5, "&:hover": { opacity: 1, color: "error.main" } }}
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                }
              >
                <ListItemButton
                  selected={selected?.id === p.id}
                  onClick={() => setSelected(p)}
                  sx={{ borderRadius: 1, mx: 0.5 }}
                >
                  <ListItemText
                    primary={p.name}
                    secondary={`${p.steps.length} step${p.steps.length !== 1 ? "s" : ""}`}
                    primaryTypographyProps={{ variant: "body2", noWrap: true }}
                    secondaryTypographyProps={{ variant: "caption" }}
                  />
                </ListItemButton>
              </ListItem>
            ))
          )}
          {!loading && pipelines.length === 0 && (
            <ListItem>
              <ListItemText
                primary="No pipelines yet"
                secondary="Click + to create one"
                primaryTypographyProps={{ variant: "caption", color: "text.secondary" }}
                secondaryTypographyProps={{ variant: "caption" }}
              />
            </ListItem>
          )}
        </List>
      </Box>

      {/* Editor + runner */}
      <Box sx={{ flexGrow: 1, overflow: "auto", p: 2 }}>
        {selected ? (
          <PipelineEditor
            pipeline={selected}
            components={components}
            onUpdateSteps={updateSteps}
          />
        ) : (
          <Box sx={{ textAlign: "center", mt: 8, color: "text.secondary" }}>
            <AccountTreeIcon sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
            <Typography variant="body2">Select a pipeline to edit and run it</Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}

// ── Pipeline editor + runner ───────────────────────────────────────────────────

function PipelineEditor({
  pipeline,
  components,
  onUpdateSteps,
}: {
  pipeline: Pipeline;
  components: DSPyComponent[];
  onUpdateSteps: (steps: PipelineStep[]) => void;
}) {
  const [steps, setSteps] = useState<PipelineStep[]>(pipeline.steps);
  const [dirty, setDirty] = useState(false);
  const [runInputs, setRunInputs] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<RunResult | null>(null);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    setSteps(pipeline.steps);
    setDirty(false);
    setRunResult(null);
    setRunError(null);
  }, [pipeline.id]);

  function addStep() {
    const updated = [...steps, { component_id: "" }];
    setSteps(updated);
    setDirty(true);
  }

  function removeStep(idx: number) {
    const updated = steps.filter((_, i) => i !== idx);
    setSteps(updated);
    setDirty(true);
  }

  function updateStep(idx: number, componentId: string) {
    const updated = steps.map((s, i) => (i === idx ? { ...s, component_id: componentId } : s));
    setSteps(updated);
    setDirty(true);
  }

  function save() {
    onUpdateSteps(steps);
    setDirty(false);
  }

  async function run() {
    setRunning(true);
    setRunResult(null);
    setRunError(null);
    try {
      const result = await api.runPipeline(pipeline.id, runInputs);
      setRunResult(result);
    } catch (e: any) {
      setRunError(e.message);
    } finally {
      setRunning(false);
    }
  }

  // Collect input fields from the first step
  const firstComp = components.find((c) => c.id === steps[0]?.component_id);
  const firstInputs = firstComp?.signature_fields.inputs ?? [];

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box>
        <Typography variant="h6" fontWeight={600}>
          {pipeline.name}
        </Typography>
        {pipeline.description && (
          <Typography variant="body2" color="text.secondary">
            {pipeline.description}
          </Typography>
        )}
      </Box>

      {/* Steps */}
      <Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
          <Typography variant="subtitle2" fontWeight={600} sx={{ flexGrow: 1 }}>
            Steps
          </Typography>
          {dirty && (
            <Button size="small" variant="contained" onClick={save}>
              Save changes
            </Button>
          )}
          <Button size="small" startIcon={<AddIcon />} onClick={addStep}>
            Add step
          </Button>
        </Box>

        {steps.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ py: 2 }}>
            No steps yet. Add a component step to get started.
          </Typography>
        )}

        {steps.map((step, idx) => {
          const comp = components.find((c) => c.id === step.component_id);
          return (
            <React.Fragment key={idx}>
              <Paper
                variant="outlined"
                sx={{ p: 1.5, display: "flex", alignItems: "center", gap: 1 }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ width: 24 }}>
                  {idx + 1}
                </Typography>
                <FormControl size="small" sx={{ flexGrow: 1 }}>
                  <InputLabel>Component</InputLabel>
                  <Select
                    label="Component"
                    value={step.component_id}
                    onChange={(e) => updateStep(idx, e.target.value)}
                  >
                    {components.map((c) => (
                      <MenuItem key={c.id} value={c.id}>
                        {c.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>
                {comp && (
                  <Chip
                    label={comp.module_type}
                    size="small"
                    variant="outlined"
                    sx={{ flexShrink: 0 }}
                  />
                )}
                <IconButton
                  size="small"
                  onClick={() => removeStep(idx)}
                  sx={{ color: "error.main", opacity: 0.6, "&:hover": { opacity: 1 } }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              </Paper>
              {idx < steps.length - 1 && (
                <Box sx={{ display: "flex", justifyContent: "center", my: 0.5 }}>
                  <ArrowDownwardIcon fontSize="small" color="disabled" />
                </Box>
              )}
            </React.Fragment>
          );
        })}
      </Box>

      {/* Runner */}
      {steps.length > 0 && steps[0]?.component_id && (
        <Box>
          <Divider sx={{ mb: 2 }} />
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            Run pipeline
          </Typography>
          {firstInputs.map((f) => (
            <TextField
              key={f.name}
              label={f.name}
              helperText={f.desc || `Input for the first step (${firstComp?.name})`}
              value={runInputs[f.name] ?? ""}
              onChange={(e) => setRunInputs({ ...runInputs, [f.name]: e.target.value })}
              multiline
              minRows={2}
              size="small"
              fullWidth
              sx={{ mb: 1.5 }}
            />
          ))}
          <Button
            variant="contained"
            startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
            onClick={run}
            disabled={running || dirty}
          >
            {running ? "Running…" : "Run Pipeline"}
          </Button>
          {dirty && (
            <Typography variant="caption" color="warning.main" sx={{ ml: 1 }}>
              Save changes first
            </Typography>
          )}

          {runError && (
            <Alert severity="error" variant="outlined" sx={{ mt: 2 }}>
              {runError}
            </Alert>
          )}

          {runResult && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Pipeline output
              </Typography>
              {Object.entries(runResult.outputs)
                .filter(([k]) => k !== "step_results")
                .map(([k, v]) => (
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
      )}
    </Box>
  );
}
