/**
 * FilesystemPanel — tree navigator + file viewer + operations.
 *
 * Features:
 *  - Directory tree rooted at workspace_root
 *  - File content viewer (syntax highlighted)
 *  - Actions: New File, New Folder, Delete, Rename
 *  - Destructive actions trigger ConfirmDialog
 */

import CreateNewFolderOutlinedIcon from "@mui/icons-material/CreateNewFolderOutlined";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import DriveFileRenameOutlineIcon from "@mui/icons-material/DriveFileRenameOutline";
import FolderIcon from "@mui/icons-material/Folder";
import InsertDriveFileOutlinedIcon from "@mui/icons-material/InsertDriveFileOutlined";
import NoteAddOutlinedIcon from "@mui/icons-material/NoteAddOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import {
  Alert,
  Box,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Button,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import * as api from "./api";
import ConfirmDialog from "./ConfirmDialog";
import type { ConfirmationRequest, FilesystemEntry, ToolResult } from "./types";

function isConfirmation(
  r: ToolResult | ConfirmationRequest,
): r is ConfirmationRequest {
  return (r as ConfirmationRequest).requires_confirmation === true;
}

function getLanguage(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  const map: Record<string, string> = {
    ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
    py: "python", rs: "rust", go: "go", json: "json", md: "markdown",
    toml: "toml", yaml: "yaml", yml: "yaml", sh: "bash", bash: "bash",
    html: "html", css: "css", txt: "text",
  };
  return map[ext] ?? "text";
}

export default function FilesystemPanel() {
  const [workspaceRoot, setWorkspaceRoot] = useState("");
  const [currentPath, setCurrentPath] = useState(".");
  const [entries, setEntries] = useState<FilesystemEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [contentLoading, setContentLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<ConfirmationRequest | null>(null);
  const [pendingAction, setPendingAction] = useState<(() => Promise<void>) | null>(null);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [createName, setCreateName] = useState("");
  const [createIsDir, setCreateIsDir] = useState(false);
  const [renameDialogOpen, setRenameDialogOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState("");
  const [renameTo, setRenameTo] = useState("");

  useEffect(() => {
    api.getWorkspaceRoot().then((r) => setWorkspaceRoot(r.workspace_root));
    loadDir(".");
  }, []);

  async function loadDir(path: string) {
    setLoading(true);
    setError(null);
    try {
      const result = await api.listDirectory(path);
      if (result.success) {
        setCurrentPath(path);
        setEntries(result.metadata.entries as FilesystemEntry[]);
      } else {
        setError(result.error ?? "Failed to list directory");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function openFile(name: string) {
    const filePath = joinPath(currentPath, name);
    setSelectedFile(filePath);
    setContentLoading(true);
    try {
      const result = await api.readFile(filePath);
      if (result.success) {
        setFileContent(result.output);
      } else {
        setFileContent(`[Error reading file: ${result.error}]`);
      }
    } catch (e: any) {
      setFileContent(`[Error: ${e.message}]`);
    } finally {
      setContentLoading(false);
    }
  }

  function navigateUp() {
    if (currentPath === ".") return;
    const parts = currentPath.split("/");
    parts.pop();
    loadDir(parts.join("/") || ".");
  }

  function joinPath(base: string, name: string) {
    return base === "." ? name : `${base}/${name}`;
  }

  async function handleCreateConfirm() {
    if (!createName.trim()) return;
    const newPath = joinPath(currentPath, createName);
    try {
      const result = await api.createPath(newPath, createIsDir);
      if (result.success) {
        await loadDir(currentPath);
      } else {
        setError(result.error ?? "Create failed");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setCreateDialogOpen(false);
      setCreateName("");
    }
  }

  async function handleDelete(name: string) {
    const targetPath = joinPath(currentPath, name);
    const entry = entries.find((e) => e.name === name);
    try {
      const response = await api.deletePath(targetPath, entry?.type === "dir");
      if (isConfirmation(response)) {
        setConfirmation(response);
        setPendingAction(() => async () => {
          await loadDir(currentPath);
          if (selectedFile === targetPath) {
            setSelectedFile(null);
            setFileContent("");
          }
        });
      } else {
        await loadDir(currentPath);
        if (selectedFile === targetPath) {
          setSelectedFile(null);
          setFileContent("");
        }
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function handleRenameConfirm() {
    if (!renameTo.trim()) return;
    const srcPath = joinPath(currentPath, renameTarget);
    const destPath = joinPath(currentPath, renameTo);
    try {
      const response = await api.movePath(srcPath, destPath);
      if (isConfirmation(response)) {
        setConfirmation(response);
        setPendingAction(() => async () => {
          await loadDir(currentPath);
        });
      } else {
        await loadDir(currentPath);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRenameDialogOpen(false);
      setRenameTarget("");
      setRenameTo("");
    }
  }

  async function handleConfirmDialogConfirm(token: string) {
    setConfirmation(null);
    try {
      await api.confirmAction(token);
      if (pendingAction) await pendingAction();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setPendingAction(null);
    }
  }

  async function handleConfirmDialogCancel(token: string) {
    setConfirmation(null);
    setPendingAction(null);
    try {
      await api.cancelConfirmation(token);
    } catch {
      // ignore
    }
  }

  const displayPath = workspaceRoot
    ? currentPath === "."
      ? workspaceRoot
      : `${workspaceRoot}/${currentPath}`
    : currentPath;

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left: directory tree */}
      <Box
        sx={{
          width: 280,
          flexShrink: 0,
          borderRight: "1px solid",
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Toolbar */}
        <Box sx={{ p: 1, display: "flex", alignItems: "center", gap: 0.5, flexWrap: "wrap" }}>
          <Typography
            variant="caption"
            sx={{ flexGrow: 1, fontFamily: "monospace", color: "text.secondary" }}
            noWrap
            title={displayPath}
          >
            {displayPath}
          </Typography>
          <Tooltip title="Refresh">
            <IconButton size="small" onClick={() => loadDir(currentPath)}>
              <RefreshIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="New file">
            <IconButton
              size="small"
              color="primary"
              onClick={() => { setCreateIsDir(false); setCreateDialogOpen(true); }}
            >
              <NoteAddOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="New folder">
            <IconButton
              size="small"
              color="primary"
              onClick={() => { setCreateIsDir(true); setCreateDialogOpen(true); }}
            >
              <CreateNewFolderOutlinedIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>

        {error && (
          <Alert severity="error" variant="outlined" sx={{ mx: 1, mb: 0.5 }} onClose={() => setError(null)}>
            {error}
          </Alert>
        )}

        {/* Up navigation */}
        {currentPath !== "." && (
          <ListItemButton onClick={navigateUp} sx={{ py: 0.3, px: 1 }}>
            <ListItemText
              primary=".."
              primaryTypographyProps={{ variant: "body2", fontFamily: "monospace" }}
            />
          </ListItemButton>
        )}

        {/* Entries */}
        {loading ? (
          <Box sx={{ display: "flex", justifyContent: "center", p: 2 }}>
            <CircularProgress size={20} />
          </Box>
        ) : (
          <List dense sx={{ overflow: "auto", flexGrow: 1, py: 0 }}>
            {entries.map((entry) => (
              <ListItem
                key={entry.name}
                disablePadding
                secondaryAction={
                  <Box>
                    <Tooltip title="Rename">
                      <IconButton
                        size="small"
                        sx={{ opacity: 0, ".MuiListItem-root:hover &": { opacity: 0.7 } }}
                        onClick={(e) => {
                          e.stopPropagation();
                          setRenameTarget(entry.name);
                          setRenameTo(entry.name);
                          setRenameDialogOpen(true);
                        }}
                      >
                        <DriveFileRenameOutlineIcon sx={{ fontSize: 14 }} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton
                        size="small"
                        sx={{ opacity: 0, ".MuiListItem-root:hover &": { opacity: 0.7 }, color: "error.main" }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDelete(entry.name);
                        }}
                      >
                        <DeleteOutlineIcon sx={{ fontSize: 14 }} />
                      </IconButton>
                    </Tooltip>
                  </Box>
                }
              >
                <ListItemButton
                  selected={selectedFile === joinPath(currentPath, entry.name)}
                  onClick={() => {
                    if (entry.type === "dir") {
                      loadDir(joinPath(currentPath, entry.name));
                    } else {
                      openFile(entry.name);
                    }
                  }}
                  sx={{ py: 0.3, px: 1, borderRadius: 0 }}
                >
                  <ListItemIcon sx={{ minWidth: 28 }}>
                    {entry.type === "dir" ? (
                      <FolderIcon sx={{ fontSize: 16, color: "primary.light" }} />
                    ) : (
                      <InsertDriveFileOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} />
                    )}
                  </ListItemIcon>
                  <ListItemText
                    primary={entry.name}
                    secondary={
                      entry.type === "file" && entry.size !== undefined
                        ? formatBytes(entry.size)
                        : undefined
                    }
                    primaryTypographyProps={{
                      variant: "body2",
                      fontFamily: "monospace",
                      fontSize: "0.78rem",
                      noWrap: true,
                    }}
                    secondaryTypographyProps={{ variant: "caption" }}
                  />
                </ListItemButton>
              </ListItem>
            ))}
            {entries.length === 0 && !loading && (
              <ListItem>
                <ListItemText
                  primary="Empty directory"
                  primaryTypographyProps={{ variant: "caption", color: "text.disabled" }}
                />
              </ListItem>
            )}
          </List>
        )}
      </Box>

      {/* Right: file viewer */}
      <Box sx={{ flexGrow: 1, overflow: "auto", position: "relative" }}>
        {contentLoading && (
          <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
            <CircularProgress size={24} />
          </Box>
        )}
        {!contentLoading && selectedFile && (
          <>
            <Box sx={{ px: 2, py: 1, borderBottom: "1px solid", borderColor: "divider" }}>
              <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                {selectedFile}
              </Typography>
            </Box>
            <SyntaxHighlighter
              language={getLanguage(selectedFile)}
              style={vscDarkPlus}
              customStyle={{ margin: 0, borderRadius: 0, minHeight: "100%", fontSize: "0.78rem" }}
              showLineNumbers
            >
              {fileContent}
            </SyntaxHighlighter>
          </>
        )}
        {!contentLoading && !selectedFile && (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
            <Typography variant="body2" color="text.disabled">
              Select a file to view its contents
            </Typography>
          </Box>
        )}
      </Box>

      {/* Create dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Create {createIsDir ? "Folder" : "File"}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            label="Name"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateConfirm()}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateConfirm} disabled={!createName.trim()}>
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Rename dialog */}
      <Dialog open={renameDialogOpen} onClose={() => setRenameDialogOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Rename</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            size="small"
            label="New name"
            value={renameTo}
            onChange={(e) => setRenameTo(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRenameConfirm()}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRenameDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleRenameConfirm} disabled={!renameTo.trim()}>
            Rename
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirmation dialog */}
      {confirmation && (
        <ConfirmDialog
          confirmation={confirmation}
          onConfirm={handleConfirmDialogConfirm}
          onCancel={handleConfirmDialogCancel}
        />
      )}
    </Box>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}
