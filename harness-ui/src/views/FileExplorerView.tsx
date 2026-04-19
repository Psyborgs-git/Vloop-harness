import { useEffect, useState, useCallback } from "react";
import {
  Box,
  Button,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  TextField,
  Typography,
} from "@mui/material";
import FolderIcon from "@mui/icons-material/Folder";
import InsertDriveFileIcon from "@mui/icons-material/InsertDriveFile";
import RefreshIcon from "@mui/icons-material/Refresh";
import SaveIcon from "@mui/icons-material/Save";
import * as tauriApi from "../api/tauri";

interface FileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size?: number;
  modified?: string;
}

export default function FileExplorerView() {
  const [cwd, setCwd] = useState("");
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [gitStatus, setGitStatus] = useState<Record<string, string[]> | null>(null);

  const loadDir = useCallback(
    async (path: string) => {
      try {
        const result = await tauriApi.fsList(path);
        setEntries(result as FileEntry[]);
        setCwd(path);
        setSelectedFile(null);
        setFileContent("");
        setDirty(false);
      } catch {
        /* empty */
      }
    },
    []
  );

  useEffect(() => {
    // Start at home dir
    loadDir(".");
  }, [loadDir]);

  const openFile = async (path: string) => {
    try {
      const content = await tauriApi.fsRead(path);
      setSelectedFile(path);
      setFileContent(content);
      setDirty(false);
    } catch {
      /* empty */
    }
  };

  const saveFile = async () => {
    if (!selectedFile) return;
    await tauriApi.fsWrite(selectedFile, fileContent);
    setDirty(false);
  };

  const refreshGitStatus = async () => {
    try {
      const s = await tauriApi.fsGitStatus(cwd);
      setGitStatus(s as Record<string, string[]>);
    } catch {
      setGitStatus(null);
    }
  };

  const sorted = [...entries].sort((a, b) => {
    if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* File tree */}
      <Box
        sx={{
          width: 240,
          borderRight: 1,
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        <Box sx={{ p: 1, display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="caption" noWrap sx={{ flex: 1, opacity: 0.7 }}>
            {cwd || "."}
          </Typography>
          <IconButton size="small" onClick={() => loadDir(cwd)}>
            <RefreshIcon fontSize="small" />
          </IconButton>
        </Box>
        <Divider />
        <List dense sx={{ overflowY: "auto", flex: 1 }}>
          {cwd && (
            <ListItemButton onClick={() => loadDir(cwd.includes("/") ? cwd.split("/").slice(0, -1).join("/") || "/" : ".")}>
              <ListItemText primary=".." />
            </ListItemButton>
          )}
          {sorted.map((entry) => (
            <ListItemButton
              key={entry.path}
              selected={selectedFile === entry.path}
              onClick={() =>
                entry.is_dir ? loadDir(entry.path) : openFile(entry.path)
              }
            >
              <ListItemIcon sx={{ minWidth: 28 }}>
                {entry.is_dir ? (
                  <FolderIcon fontSize="small" color="primary" />
                ) : (
                  <InsertDriveFileIcon fontSize="small" />
                )}
              </ListItemIcon>
              <ListItemText
                primary={
                  <Typography variant="body2" noWrap>
                    {entry.name}
                  </Typography>
                }
              />
            </ListItemButton>
          ))}
        </List>
        <Divider />
        <Button size="small" onClick={refreshGitStatus} sx={{ m: 1 }}>
          Git Status
        </Button>
        {gitStatus && (
          <Box sx={{ p: 1, fontSize: 11, overflowY: "auto", maxHeight: 120 }}>
            <pre style={{ margin: 0 }}>{JSON.stringify(gitStatus, null, 2)}</pre>
          </Box>
        )}
      </Box>

      {/* Editor */}
      <Box sx={{ flex: 1, display: "flex", flexDirection: "column", p: 1, overflow: "hidden" }}>
        {selectedFile ? (
          <>
            <Box display="flex" alignItems="center" gap={1} mb={1}>
              <Typography variant="caption" noWrap sx={{ flex: 1, opacity: 0.7 }}>
                {selectedFile}
              </Typography>
              <Button
                size="small"
                variant="contained"
                startIcon={<SaveIcon />}
                onClick={saveFile}
                disabled={!dirty}
              >
                Save
              </Button>
            </Box>
            <TextField
              multiline
              fullWidth
              value={fileContent}
              onChange={(e) => {
                setFileContent(e.target.value);
                setDirty(true);
              }}
              inputProps={{ style: { fontFamily: "monospace", fontSize: 12 } }}
              sx={{ flex: 1, "& .MuiInputBase-root": { alignItems: "flex-start" } }}
            />
          </>
        ) : (
          <Box
            display="flex"
            alignItems="center"
            justifyContent="center"
            height="100%"
          >
            <Typography variant="body2" color="text.secondary">
              Select a file to edit
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
