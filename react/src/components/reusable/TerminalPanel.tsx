/**
 * TerminalPanel — command execution panel within the workspace.
 *
 * Features:
 *  - CWD display + relative path selector
 *  - Command input (Enter to run, ↑/↓ for history)
 *  - Output area with ANSI-stripped rendering
 *  - Clear / copy actions
 *  - Exit code badge and duration display
 *  - Inline error / policy denial messages
 *  - Confirmation dialog for caution-level commands
 */

import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import ClearIcon from "@mui/icons-material/Clear";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import {
  Box,
  Chip,
  CircularProgress,
  IconButton,
  InputAdornment,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";

import * as api from "./api";
import ConfirmDialog from "./ConfirmDialog";
import type { ConfirmationRequest, ToolResult } from "./types";

function isConfirmation(r: ToolResult | ConfirmationRequest): r is ConfirmationRequest {
  return (r as ConfirmationRequest).requires_confirmation === true;
}

interface OutputEntry {
  command: string;
  result: ToolResult;
  duration_ms?: number;
  cwd: string;
}

export default function TerminalPanel() {
  const [workspaceRoot, setWorkspaceRoot] = useState<string>("");
  const [cwdRelative, setCwdRelative] = useState(".");
  const [command, setCommand] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [outputs, setOutputs] = useState<OutputEntry[]>([]);
  const [running, setRunning] = useState(false);
  const [confirmation, setConfirmation] = useState<ConfirmationRequest | null>(null);
  const [pendingCommand, setPendingCommand] = useState<string | null>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.getWorkspaceRoot().then((r) => setWorkspaceRoot(r.workspace_root));
  }, []);

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [outputs]);

  async function runCommand(cmd: string) {
    if (!cmd.trim() || running) return;
    setRunning(true);
    try {
      const response = await api.executeTerminal(cmd, cwdRelative);
      if (isConfirmation(response)) {
        setPendingCommand(cmd);
        setConfirmation(response);
      } else {
        addOutput(cmd, response);
        setHistory((h) => [cmd, ...h.slice(0, 99)]);
        setHistoryIdx(-1);
        setCommand("");
      }
    } catch (e: any) {
      addOutput(cmd, {
        success: false,
        output: "",
        error: e.message,
        exit_code: null,
        metadata: {},
      });
    } finally {
      setRunning(false);
    }
  }

  function addOutput(cmd: string, result: ToolResult) {
    setOutputs((prev) => [
      ...prev,
      {
        command: cmd,
        result,
        duration_ms: result.metadata?.duration_ms as number | undefined,
        cwd: cwdRelative,
      },
    ]);
  }

  async function handleConfirm(token: string) {
    setConfirmation(null);
    if (!pendingCommand) return;
    setRunning(true);
    try {
      const result = await api.confirmAction(token);
      addOutput(pendingCommand, result);
      setHistory((h) => [pendingCommand, ...h.slice(0, 99)]);
      setHistoryIdx(-1);
      setCommand("");
    } catch (e: any) {
      addOutput(pendingCommand, {
        success: false,
        output: "",
        error: e.message,
        exit_code: null,
        metadata: {},
      });
    } finally {
      setRunning(false);
      setPendingCommand(null);
    }
  }

  async function handleCancel(token: string) {
    setConfirmation(null);
    setPendingCommand(null);
    try {
      await api.cancelConfirmation(token);
    } catch {
      // ignore
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      runCommand(command);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      const newIdx = Math.min(historyIdx + 1, history.length - 1);
      setHistoryIdx(newIdx);
      setCommand(history[newIdx] ?? "");
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      const newIdx = Math.max(historyIdx - 1, -1);
      setHistoryIdx(newIdx);
      setCommand(newIdx === -1 ? "" : history[newIdx] ?? "");
    }
  }

  function copyAll() {
    const text = outputs
      .map((o) => `$ ${o.command}\n${o.result.output}${o.result.error ? "\n[error] " + o.result.error : ""}`)
      .join("\n\n");
    navigator.clipboard.writeText(text);
  }

  const displayCwd = workspaceRoot
    ? cwdRelative === "."
      ? workspaceRoot
      : `${workspaceRoot}/${cwdRelative}`
    : cwdRelative;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", p: 2, gap: 1.5 }}>
      {/* CWD bar */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>
          cwd:
        </Typography>
        <TextField
          size="small"
          value={cwdRelative}
          onChange={(e) => setCwdRelative(e.target.value || ".")}
          placeholder="."
          sx={{ width: 240 }}
          inputProps={{ style: { fontFamily: "monospace", fontSize: "0.78rem" } }}
        />
        <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace" }}>
          → {displayCwd}
        </Typography>
      </Box>

      {/* Output area */}
      <Box
        ref={outputRef}
        sx={{
          flexGrow: 1,
          overflow: "auto",
          bgcolor: "#0a0a0f",
          borderRadius: 1,
          border: "1px solid",
          borderColor: "divider",
          p: 1.5,
          fontFamily: "monospace",
          fontSize: "0.8rem",
        }}
      >
        {outputs.length === 0 && (
          <Typography variant="caption" color="text.disabled">
            No output yet. Run a command below.
          </Typography>
        )}
        {outputs.map((entry, idx) => (
          <Box key={idx} sx={{ mb: 1.5 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.3 }}>
              <Typography
                variant="caption"
                sx={{ color: "primary.light", fontFamily: "monospace" }}
              >
                $ {entry.command}
              </Typography>
              <Box sx={{ flexGrow: 1 }} />
              {entry.result.exit_code !== null && (
                <Chip
                  label={`exit ${entry.result.exit_code}`}
                  size="small"
                  color={entry.result.success ? "success" : "error"}
                  variant="outlined"
                  icon={
                    entry.result.success ? (
                      <CheckCircleOutlineIcon sx={{ fontSize: "12px !important" }} />
                    ) : (
                      <ErrorOutlineIcon sx={{ fontSize: "12px !important" }} />
                    )
                  }
                  sx={{ height: 18, fontSize: "0.68rem" }}
                />
              )}
              {entry.duration_ms !== undefined && (
                <Typography variant="caption" color="text.disabled">
                  {entry.duration_ms}ms
                </Typography>
              )}
            </Box>
            {entry.result.output && (
              <Typography
                component="pre"
                sx={{
                  m: 0,
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                  color: "text.primary",
                  fontSize: "0.78rem",
                }}
              >
                {entry.result.output}
              </Typography>
            )}
            {entry.result.error && !entry.result.success && (
              <Typography
                component="pre"
                sx={{
                  m: 0,
                  color: "error.light",
                  whiteSpace: "pre-wrap",
                  fontSize: "0.78rem",
                }}
              >
                {entry.result.error}
              </Typography>
            )}
          </Box>
        ))}
      </Box>

      {/* Action bar */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 0.5 }}>
        <Tooltip title="Copy all output">
          <IconButton size="small" onClick={copyAll} disabled={outputs.length === 0}>
            <ContentCopyIcon fontSize="small" />
          </IconButton>
        </Tooltip>
        <Tooltip title="Clear output">
          <IconButton size="small" onClick={() => setOutputs([])} disabled={outputs.length === 0}>
            <ClearIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Command input */}
      <TextField
        fullWidth
        size="small"
        placeholder="Enter command… (↑/↓ for history, Enter to run)"
        value={command}
        onChange={(e) => setCommand(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={running}
        inputProps={{ style: { fontFamily: "monospace" } }}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <Typography sx={{ color: "primary.main", fontFamily: "monospace", fontSize: "0.85rem" }}>
                $
              </Typography>
            </InputAdornment>
          ),
          endAdornment: (
            <InputAdornment position="end">
              {running ? (
                <CircularProgress size={16} />
              ) : (
                <Tooltip title="Run (Enter)">
                  <IconButton
                    size="small"
                    onClick={() => runCommand(command)}
                    disabled={!command.trim()}
                  >
                    <PlayArrowIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </InputAdornment>
          ),
        }}
      />

      {/* Confirmation dialog */}
      {confirmation && (
        <ConfirmDialog
          confirmation={confirmation}
          onConfirm={handleConfirm}
          onCancel={handleCancel}
        />
      )}
    </Box>
  );
}
