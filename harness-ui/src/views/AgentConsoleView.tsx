import { useState, useEffect, useRef } from "react";
import {
  Box,
  Button,
  CircularProgress,
  Divider,
  FormControl,
  InputLabel,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  TextField,
  Typography,
  Chip,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import * as inferenceApi from "../api/inference";
import * as tauriApi from "../api/tauri";
import { useAgentStore } from "../stores/agentStore";

const AGENT_LOOPS = [
  "chain_of_thought",
  "react",
  "plan_execute",
  "tool_call",
  "multi_agent",
];

export default function AgentConsoleView() {
  const [task, setTask] = useState("");
  const [selectedLoop, setSelectedLoop] = useState("chain_of_thought");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const { runs, setRuns, selectedRun, selectRun } = useAgentStore();
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    tauriApi
      .dbGetAgentRuns(50, 0)
      .then((r) => setRuns(r as never[]))
      .catch(() => {});

    // Connect WebSocket stream
    wsRef.current = inferenceApi.createStreamWebSocket((msg) => {
      console.debug("ws:", msg);
    });

    return () => {
      wsRef.current?.close();
    };
  }, [setRuns]);

  const runAgent = async () => {
    if (!task.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const res = await inferenceApi.agentRun(selectedLoop, task);
      setResult(res as Record<string, unknown>);
      // Refresh runs list
      tauriApi
        .dbGetAgentRuns(50, 0)
        .then((r) => setRuns(r as never[]))
        .catch(() => {});
    } catch (e) {
      setResult({ error: String(e) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Sidebar: run history */}
      <Box
        sx={{
          width: 220,
          borderRight: 1,
          borderColor: "divider",
          overflowY: "auto",
          p: 1,
        }}
      >
        <Typography variant="caption" color="text.secondary" sx={{ px: 1 }}>
          Run History
        </Typography>
        <List dense>
          {runs.length === 0 && (
            <Typography variant="caption" sx={{ px: 1 }} color="text.disabled">
              No runs yet
            </Typography>
          )}
          {(runs as { id: string; agent_loop: string; status: string; task: string }[]).map(
            (run) => (
              <ListItemButton
                key={run.id}
                selected={selectedRun?.id === run.id}
                onClick={() => selectRun(run as never)}
                sx={{ borderRadius: 1, mb: 0.25 }}
              >
                <ListItemText
                  primary={
                    <Typography variant="body2" noWrap>
                      {run.task}
                    </Typography>
                  }
                  secondary={
                    <Box display="flex" gap={0.5} mt={0.25}>
                      <Chip
                        label={run.agent_loop}
                        size="small"
                        variant="outlined"
                        sx={{ fontSize: 10, height: 18 }}
                      />
                      <Chip
                        label={run.status}
                        size="small"
                        color={run.status === "completed" ? "success" : "default"}
                        sx={{ fontSize: 10, height: 18 }}
                      />
                    </Box>
                  }
                />
              </ListItemButton>
            )
          )}
        </List>
      </Box>

      {/* Main area */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", p: 2, overflow: "hidden" }}>
        <Typography variant="h6" gutterBottom>
          Agent Console
        </Typography>

        <Box display="flex" gap={1} mb={1}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Agent Loop</InputLabel>
            <Select
              value={selectedLoop}
              label="Agent Loop"
              onChange={(e) => setSelectedLoop(e.target.value)}
            >
              {AGENT_LOOPS.map((l) => (
                <MenuItem key={l} value={l}>
                  {l.replace(/_/g, " ")}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>

        <TextField
          multiline
          rows={3}
          fullWidth
          label="Task"
          placeholder="What should the agent do?"
          value={task}
          onChange={(e) => setTask(e.target.value)}
          size="small"
          sx={{ mb: 1 }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && e.ctrlKey) runAgent();
          }}
        />

        <Box display="flex" gap={1} mb={2}>
          <Button
            variant="contained"
            startIcon={loading ? <CircularProgress size={16} /> : <PlayArrowIcon />}
            onClick={runAgent}
            disabled={loading || !task.trim()}
            size="small"
          >
            {loading ? "Running…" : "Run (Ctrl+Enter)"}
          </Button>
        </Box>

        <Divider sx={{ mb: 2 }} />

        {/* Result */}
        <Box sx={{ flex: 1, overflowY: "auto" }}>
          {result && (
            <Box>
              {result.error ? (
                <Typography color="error" variant="body2">
                  {String(result.error)}
                </Typography>
              ) : (
                <>
                  <Typography variant="subtitle2" gutterBottom>
                    Answer
                  </Typography>
                  <Box
                    component="pre"
                    sx={{
                      whiteSpace: "pre-wrap",
                      fontSize: 13,
                      background: (t) => t.palette.action.hover,
                      p: 1.5,
                      borderRadius: 1,
                      mb: 2,
                    }}
                  >
                    {String(result.answer)}
                  </Box>
                  {result.steps && (
                    <>
                      <Typography variant="subtitle2" gutterBottom>
                        Steps
                      </Typography>
                      <Box
                        component="pre"
                        sx={{
                          fontSize: 11,
                          overflowX: "auto",
                          background: (t) => t.palette.action.hover,
                          p: 1,
                          borderRadius: 1,
                        }}
                      >
                        {JSON.stringify(result.steps, null, 2)}
                      </Box>
                    </>
                  )}
                </>
              )}
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
