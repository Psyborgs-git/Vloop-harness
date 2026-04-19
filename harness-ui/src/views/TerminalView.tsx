import { useEffect, useRef, useState } from "react";
import { Box, Button, Tab, Tabs, IconButton, Typography } from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import CloseIcon from "@mui/icons-material/Close";
import * as tauriApi from "../api/tauri";
import { useTerminalStore } from "../stores/terminalStore";
import XtermInstance from "../components/shared/XtermInstance";

export default function TerminalView() {
  const { sessions, activeSessionId, setSessions, setActive, addSession, removeSession } =
    useTerminalStore();

  useEffect(() => {
    tauriApi.terminalList().then((list) => {
      setSessions(list as never[]);
      if (list.length > 0) setActive((list[0] as { id: string }).id);
    });
  }, [setSessions, setActive]);

  const createSession = async () => {
    const id = await tauriApi.terminalCreate();
    addSession({ id, shell: "default", cwd: "~", status: "running" });
    setActive(id);
  };

  const killSession = async (id: string) => {
    await tauriApi.terminalKill(id);
    removeSession(id);
  };

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <Box sx={{ display: "flex", alignItems: "center", borderBottom: 1, borderColor: "divider" }}>
        <Tabs
          value={activeSessionId ?? false}
          onChange={(_, v) => setActive(v)}
          variant="scrollable"
          scrollButtons="auto"
          sx={{ flex: 1 }}
        >
          {sessions.map((s) => (
            <Tab
              key={s.id}
              value={s.id}
              label={
                <Box display="flex" alignItems="center" gap={0.5}>
                  <span>Terminal {s.id.slice(0, 6)}</span>
                  <IconButton
                    size="small"
                    onClick={(e) => {
                      e.stopPropagation();
                      killSession(s.id);
                    }}
                    sx={{ p: 0, ml: 0.5 }}
                  >
                    <CloseIcon sx={{ fontSize: 14 }} />
                  </IconButton>
                </Box>
              }
            />
          ))}
        </Tabs>
        <Button
          size="small"
          startIcon={<AddIcon />}
          onClick={createSession}
          sx={{ mr: 1, whiteSpace: "nowrap" }}
        >
          New
        </Button>
      </Box>

      <Box sx={{ flex: 1, overflow: "hidden", position: "relative" }}>
        {sessions.length === 0 ? (
          <Box
            display="flex"
            flexDirection="column"
            alignItems="center"
            justifyContent="center"
            height="100%"
          >
            <Typography variant="body2" color="text.secondary">
              No terminal sessions
            </Typography>
            <Button onClick={createSession} startIcon={<AddIcon />} sx={{ mt: 1 }}>
              Open Terminal
            </Button>
          </Box>
        ) : (
          sessions.map((s) => (
            <Box
              key={s.id}
              sx={{
                position: "absolute",
                inset: 0,
                display: activeSessionId === s.id ? "block" : "none",
              }}
            >
              <XtermInstance sessionId={s.id} />
            </Box>
          ))
        )}
      </Box>
    </Box>
  );
}
