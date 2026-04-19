import { useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import StopIcon from "@mui/icons-material/Stop";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import ListAltIcon from "@mui/icons-material/ListAlt";
import * as tauriApi from "../api/tauri";
import { useProcessStore } from "../stores/processStore";

interface ProcessLog {
  process_id: string;
  stream: string;
  line: string;
  ts: string;
}

export default function ProcessManagerView() {
  const { processes, setProcesses } = useProcessStore();
  const [openAdd, setOpenAdd] = useState(false);
  const [logDialog, setLogDialog] = useState<{ id: string; logs: ProcessLog[] } | null>(null);
  const [form, setForm] = useState({ name: "", command: "", cwd: "", port: "" });

  const refresh = () => {
    tauriApi.processList().then((p) => setProcesses(p as never[]));
  };

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [setProcesses]);

  const startProcess = async () => {
    await tauriApi.processStart({
      name: form.name,
      command: form.command,
      cwd: form.cwd || undefined,
      port: form.port ? Number(form.port) : undefined,
    });
    setOpenAdd(false);
    refresh();
  };

  const viewLogs = async (id: string) => {
    const logs = await tauriApi.processLogs(id, 200);
    setLogDialog({ id, logs: logs as ProcessLog[] });
  };

  return (
    <Box sx={{ p: 2, height: "100%", overflow: "auto" }}>
      <Box display="flex" alignItems="center" gap={1} mb={2}>
        <Typography variant="h6">Process Manager</Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddIcon />}
          onClick={() => setOpenAdd(true)}
        >
          Add
        </Button>
        <Button size="small" onClick={refresh}>
          Refresh
        </Button>
      </Box>

      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell>
              <TableCell>Command</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>PID</TableCell>
              <TableCell>Port</TableCell>
              <TableCell>Actions</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {processes.length === 0 && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary" align="center">
                    No processes
                  </Typography>
                </TableCell>
              </TableRow>
            )}
            {(
              processes as {
                id: string;
                name: string;
                command: string;
                status: string;
                pid?: number;
                port?: number;
              }[]
            ).map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.name}</TableCell>
                <TableCell>
                  <Typography variant="body2" fontFamily="monospace" noWrap maxWidth={200}>
                    {p.command}
                  </Typography>
                </TableCell>
                <TableCell>
                  <Chip
                    label={p.status}
                    size="small"
                    color={p.status === "running" ? "success" : "default"}
                  />
                </TableCell>
                <TableCell>{p.pid ?? "—"}</TableCell>
                <TableCell>{p.port ?? "—"}</TableCell>
                <TableCell>
                  <Box display="flex" gap={0.5}>
                    <IconButton
                      size="small"
                      onClick={() => tauriApi.processStop(p.id).then(refresh)}
                      title="Stop"
                    >
                      <StopIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={() => tauriApi.processRestart(p.id).then(refresh)}
                      title="Restart"
                    >
                      <RestartAltIcon fontSize="small" />
                    </IconButton>
                    <IconButton
                      size="small"
                      onClick={() => viewLogs(p.id)}
                      title="Logs"
                    >
                      <ListAltIcon fontSize="small" />
                    </IconButton>
                  </Box>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Add process dialog */}
      <Dialog open={openAdd} onClose={() => setOpenAdd(false)} fullWidth maxWidth="xs">
        <DialogTitle>Add Process</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 1.5, pt: 2 }}>
          <TextField
            label="Name"
            size="small"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <TextField
            label="Command"
            size="small"
            value={form.command}
            onChange={(e) => setForm((f) => ({ ...f, command: e.target.value }))}
          />
          <TextField
            label="Working dir (optional)"
            size="small"
            value={form.cwd}
            onChange={(e) => setForm((f) => ({ ...f, cwd: e.target.value }))}
          />
          <TextField
            label="Port (optional)"
            size="small"
            type="number"
            value={form.port}
            onChange={(e) => setForm((f) => ({ ...f, port: e.target.value }))}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenAdd(false)}>Cancel</Button>
          <Button variant="contained" onClick={startProcess} disabled={!form.command}>
            Start
          </Button>
        </DialogActions>
      </Dialog>

      {/* Log dialog */}
      {logDialog && (
        <Dialog
          open
          onClose={() => setLogDialog(null)}
          fullWidth
          maxWidth="md"
        >
          <DialogTitle>Logs — {logDialog.id.slice(0, 8)}</DialogTitle>
          <DialogContent>
            <Box
              component="pre"
              sx={{
                fontSize: 11,
                fontFamily: "monospace",
                whiteSpace: "pre-wrap",
                maxHeight: 400,
                overflowY: "auto",
                background: (t) => t.palette.action.hover,
                p: 1,
                borderRadius: 1,
              }}
            >
              {logDialog.logs.map((l) => `[${l.ts}][${l.stream}] ${l.line}`).join("\n") ||
                "(empty)"}
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setLogDialog(null)}>Close</Button>
          </DialogActions>
        </Dialog>
      )}
    </Box>
  );
}
