/**
 * AgentRunPanel — browse, start, monitor, and control agent runs.
 *
 * Features:
 *  • List of recent runs with status chips
 *  • Start a new run with goal + autonomy mode selector
 *  • Expandable step timeline for each run
 *  • Cancel / resume controls for running/paused runs
 */

import AddIcon from "@mui/icons-material/Add";
import CancelIcon from "@mui/icons-material/Cancel";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  List,
  ListItem,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";

import * as api from "./api";
import type { AgentRun, AgentRunStep } from "./types";

interface Props {
  focusRunId?: string;
  onFocused?: () => void;
}

const STATUS_COLOR: Record<string, "default" | "warning" | "info" | "success" | "error"> = {
  pending: "default",
  running: "info",
  paused: "warning",
  completed: "success",
  cancelled: "default",
  failed: "error",
};

export default function AgentRunPanel({ focusRunId, onFocused }: Props) {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [showNew, setShowNew] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(focusRunId ?? null);
  const [expandedRun, setExpandedRun] = useState<AgentRun | null>(null);

  // New run form
  const [goal, setGoal] = useState("");
  const [autonomyMode, setAutonomyMode] = useState("suggest");
  const [context, setContext] = useState("");
  const [starting, setStarting] = useState(false);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await api.listAgentRuns(50);
      setRuns(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (focusRunId) {
      setExpandedId(focusRunId);
      onFocused?.();
    }
  }, [focusRunId, onFocused]);

  // Poll for status updates when any run is active
  useEffect(() => {
    const hasActive = runs.some((r) => r.status === "running" || r.status === "pending");
    if (hasActive && !pollingRef.current) {
      pollingRef.current = setInterval(load, 3000);
    } else if (!hasActive && pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [runs]);

  const loadRunDetail = async (runId: string) => {
    const full = await api.getAgentRun(runId);
    setExpandedRun(full);
  };

  const handleExpand = (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setExpandedRun(null);
    } else {
      setExpandedId(id);
      loadRunDetail(id);
    }
  };

  const handleStart = async () => {
    if (!goal.trim()) return;
    setStarting(true);
    try {
      const run = await api.startAgentRun({ goal, autonomy_mode: autonomyMode, context });
      setRuns((prev) => [run, ...prev]);
      setShowNew(false);
      setGoal("");
      setContext("");
      setExpandedId(run.id);
      loadRunDetail(run.id);
    } finally {
      setStarting(false);
    }
  };

  const handleCancel = async (runId: string) => {
    await api.cancelAgentRun(runId);
    load();
  };

  const handleResume = async (runId: string) => {
    await api.resumeAgentRun(runId);
    load();
    loadRunDetail(runId);
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      {/* Header toolbar */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, p: 1, flexShrink: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
          {runs.length} run{runs.length !== 1 ? "s" : ""}
        </Typography>
        <Tooltip title="Refresh">
          <IconButton size="small" onClick={load} disabled={loading}>
            {loading ? <CircularProgress size={14} /> : <RefreshIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
        <Tooltip title="New run">
          <IconButton size="small" onClick={() => setShowNew((v) => !v)}>
            <AddIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* New run form */}
      <Collapse in={showNew} unmountOnExit>
        <Box sx={{ px: 1.5, pb: 1, display: "flex", flexDirection: "column", gap: 1 }}>
          <TextField
            label="Goal"
            size="small"
            fullWidth
            multiline
            minRows={2}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
            placeholder="Describe what the agent should do…"
          />
          <FormControl size="small" fullWidth>
            <InputLabel>Autonomy mode</InputLabel>
            <Select
              label="Autonomy mode"
              value={autonomyMode}
              onChange={(e) => setAutonomyMode(e.target.value)}
            >
              <MenuItem value="observe">Observe — plan only</MenuItem>
              <MenuItem value="suggest">Suggest — plan + draft artifacts</MenuItem>
              <MenuItem value="write_approval">Write with approval</MenuItem>
              <MenuItem value="test_approval">Test with approval</MenuItem>
              <MenuItem value="autonomous">Autonomous</MenuItem>
            </Select>
          </FormControl>
          <TextField
            label="Context (optional)"
            size="small"
            fullWidth
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Additional context…"
          />
          <Button
            variant="contained"
            size="small"
            startIcon={starting ? <CircularProgress size={14} color="inherit" /> : <PlayArrowIcon />}
            disabled={!goal.trim() || starting}
            onClick={handleStart}
          >
            Start run
          </Button>
        </Box>
        <Divider />
      </Collapse>

      {/* Run list */}
      <Box sx={{ flexGrow: 1, overflowY: "auto" }}>
        {runs.length === 0 && !loading && (
          <Typography variant="caption" color="text.secondary" sx={{ p: 2, display: "block" }}>
            No agent runs yet. Click + to start one.
          </Typography>
        )}
        <List dense disablePadding>
          {runs.map((run) => (
            <Box key={run.id}>
              <ListItem
                disablePadding
                sx={{
                  px: 1.5,
                  py: 0.75,
                  cursor: "pointer",
                  "&:hover": { bgcolor: "action.hover" },
                  bgcolor: expandedId === run.id ? "action.selected" : "transparent",
                }}
                onClick={() => handleExpand(run.id)}
              >
                <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                  <Typography
                    variant="body2"
                    noWrap
                    title={run.goal}
                    sx={{ fontSize: "0.82rem" }}
                  >
                    {run.goal}
                  </Typography>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.25 }}>
                    <Chip
                      label={run.status}
                      size="small"
                      color={STATUS_COLOR[run.status] ?? "default"}
                      sx={{ fontSize: "0.7rem", height: 18 }}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {run.autonomy_mode}
                    </Typography>
                  </Box>
                </Box>
                <Box sx={{ display: "flex", alignItems: "center", ml: 1 }}>
                  {(run.status === "running" || run.status === "pending") && (
                    <Tooltip title="Cancel">
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); handleCancel(run.id); }}
                      >
                        <CancelIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  {run.status === "paused" && (
                    <Tooltip title="Resume">
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); handleResume(run.id); }}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  )}
                  {expandedId === run.id ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                </Box>
              </ListItem>

              {/* Step timeline */}
              <Collapse in={expandedId === run.id} unmountOnExit>
                <Box sx={{ pl: 2, pr: 1, pb: 1, borderBottom: "1px solid", borderColor: "divider" }}>
                  {expandedRun?.id === run.id ? (
                    <StepTimeline run={expandedRun} />
                  ) : (
                    <CircularProgress size={16} sx={{ my: 1 }} />
                  )}
                </Box>
              </Collapse>
            </Box>
          ))}
        </List>
      </Box>
    </Box>
  );
}

function StepTimeline({ run }: { run: AgentRun }) {
  const steps = run.steps ?? [];

  if (steps.length === 0) {
    return (
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", py: 0.5 }}>
        No steps recorded yet.
      </Typography>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, pt: 0.5 }}>
      {steps.map((step) => (
        <StepRow key={step.id} step={step} />
      ))}
    </Box>
  );
}

function StepRow({ step }: { step: AgentRunStep }) {
  const [open, setOpen] = useState(false);

  const icon =
    step.status === "completed" ? (
      <CheckCircleIcon sx={{ fontSize: 14, color: "success.main" }} />
    ) : step.status === "failed" ? (
      <ErrorIcon sx={{ fontSize: 14, color: "error.main" }} />
    ) : step.status === "skipped" ? (
      <CheckCircleIcon sx={{ fontSize: 14, color: "text.disabled" }} />
    ) : (
      <CircularProgress size={12} />
    );

  return (
    <Box>
      <Box
        sx={{ display: "flex", alignItems: "center", gap: 0.5, cursor: "pointer" }}
        onClick={() => setOpen((v) => !v)}
      >
        {icon}
        <Typography variant="caption" sx={{ flexGrow: 1, fontSize: "0.75rem" }} noWrap>
          [{step.step_type}]{step.tool_name ? ` · ${step.tool_name}` : ""}
        </Typography>
        {step.duration_ms !== null && (
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.7rem" }}>
            {step.duration_ms}ms
          </Typography>
        )}
        {open ? <ExpandLessIcon sx={{ fontSize: 12 }} /> : <ExpandMoreIcon sx={{ fontSize: 12 }} />}
      </Box>
      <Collapse in={open} unmountOnExit>
        <Box
          component="pre"
          sx={{
            fontSize: "0.7rem",
            overflow: "auto",
            maxHeight: 180,
            bgcolor: "background.default",
            p: 0.75,
            borderRadius: 1,
            mt: 0.5,
            whiteSpace: "pre-wrap",
            wordBreak: "break-all",
          }}
        >
          {step.error
            ? `ERROR: ${step.error}`
            : JSON.stringify(step.output_data, null, 2)}
        </Box>
      </Collapse>
    </Box>
  );
}
