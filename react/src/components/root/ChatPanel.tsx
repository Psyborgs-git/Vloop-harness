/**
 * ChatPanel — root chat interface for interacting with DSPy components.
 *
 * Features:
 *  • Session list sidebar
 *  • Message thread with markdown rendering and code block highlighting
 *  • Composer with [⚙ Tools], [◈ Components], [+ View] action buttons
 *  • Mobile: action buttons collapse behind [+] expander
 *  • Auto-saves AI-generated component/pipeline/view artifacts
 *  • Artifact chips (Component saved / Pipeline saved / → Open View)
 */

import AccountTreeIcon from "@mui/icons-material/AccountTree";
import AddIcon from "@mui/icons-material/Add";
import CodeIcon from "@mui/icons-material/Code";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import SendIcon from "@mui/icons-material/Send";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import TerminalIcon from "@mui/icons-material/Terminal";
import WebIcon from "@mui/icons-material/Web";
import {
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Collapse,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import * as api from "./api";
import GenerateViewDialog from "./GenerateViewDialog";
import type { ChatMessage, ChatSession, ContextPanelState, DSPyComponent, GeneratedView, ToolCatalogEntry } from "./types";

interface Props {
  focusSessionId?: string | null;
  onFocused?: () => void;
  onOpenPanel?: (type: ContextPanelState["type"], id?: string) => void;
  onOpenWorkspace?: (url: string, title: string) => void;
}

export default function ChatPanel({ focusSessionId, onFocused, onOpenPanel, onOpenWorkspace }: Props) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));

  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Composer action state
  const [actionsExpanded, setActionsExpanded] = useState(false);
  const [toolsAnchor, setToolsAnchor] = useState<null | HTMLElement>(null);
  const [compsAnchor, setCompsAnchor] = useState<null | HTMLElement>(null);
  const [toolList, setToolList] = useState<ToolCatalogEntry[]>([]);
  const [compList, setCompList] = useState<DSPyComponent[]>([]);
  const [viewDialogOpen, setViewDialogOpen] = useState(false);

  // Track whether tool/component lists have been fetched (even if empty)
  const toolListLoadedRef = useRef(false);
  const toolListLoadingRef = useRef(false);
  const compListLoadedRef = useRef(false);
  const compListLoadingRef = useRef(false);

  // ── Load sessions on mount ────────────────────────────────────────────────

  useEffect(() => {
    api.listSessions().then((s) => {
      setSessions(s);
      if (s.length > 0) loadMessages(s[0].id);
    });
  }, []);

  // ── Jump to session from command palette ──────────────────────────────────

  useEffect(() => {
    if (!focusSessionId || sessions.length === 0) return;
    const target = sessions.find((s) => s.id === focusSessionId);
    if (target) {
      loadMessages(target.id);
      onFocused?.();
    }
  }, [focusSessionId, sessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Session management ────────────────────────────────────────────────────

  async function newSession() {
    const s = await api.createSession();
    setSessions((prev) => [s, ...prev]);
    setActiveId(s.id);
    setMessages([]);
  }

  async function loadMessages(sessionId: string) {
    setActiveId(sessionId);
    const msgs = await api.listMessages(sessionId);
    setMessages(msgs);
  }

  async function removeSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    await api.deleteSession(id);
    setSessions((prev) => prev.filter((s) => s.id !== id));
    if (activeId === id) {
      setActiveId(null);
      setMessages([]);
    }
  }

  // ── Send message ──────────────────────────────────────────────────────────

  async function send() {
    if (!input.trim() || !activeId || sending) return;
    const userContent = input.trim();
    setInput("");
    setSending(true);

    const tempUserMsg: ChatMessage = {
      id: `tmp-${Date.now()}`,
      session_id: activeId,
      role: "user",
      content: userContent,
      meta: {},
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, tempUserMsg]);

    try {
      await api.sendMessage(activeId, userContent);
      const msgs = await api.listMessages(activeId);
      setMessages(msgs);
    } catch {
      setMessages((prev) =>
        prev.filter((m) => m.id !== tempUserMsg.id).concat({
          id: `err-${Date.now()}`,
          session_id: activeId,
          role: "assistant",
          content: "Sorry, something went wrong. Please try again.",
          meta: {},
          created_at: new Date().toISOString(),
        })
      );
    } finally {
      setSending(false);
    }
  }

  // ── Tools menu ────────────────────────────────────────────────────────────

  async function openToolsMenu(e: React.MouseEvent<HTMLElement>) {
    setToolsAnchor(e.currentTarget);
    if (toolListLoadedRef.current || toolListLoadingRef.current) return;
    toolListLoadingRef.current = true;
    try {
      const tools = await api.listTools().catch(() => []);
      setToolList(tools);
      toolListLoadedRef.current = true;
    } finally {
      toolListLoadingRef.current = false;
    }
  }

  function selectTool(name: string) {
    setInput((prev) => `${prev}@tool:${name} `.trimStart());
    setToolsAnchor(null);
    onOpenPanel?.("tools");
  }

  // ── Components menu ───────────────────────────────────────────────────────

  async function openCompsMenu(e: React.MouseEvent<HTMLElement>) {
    setCompsAnchor(e.currentTarget);
    if (compListLoadedRef.current || compListLoadingRef.current) return;
    compListLoadingRef.current = true;
    try {
      const comps = await api.listComponents().catch(() => []);
      setCompList(comps);
      compListLoadedRef.current = true;
    } finally {
      compListLoadingRef.current = false;
    }
  }

  function selectComponent(id: string, name: string) {
    setInput((prev) => `${prev}@component:${name} `.trimStart());
    setCompsAnchor(null);
    onOpenPanel?.("dspy", id);
  }

  // ── View generated ────────────────────────────────────────────────────────

  function handleViewGenerated(view: GeneratedView) {
    // Reload messages in case the session was active during view generation
    if (activeId) {
      api.listMessages(activeId).then(setMessages);
    }
    onOpenPanel?.("view", view.id);
    onOpenWorkspace?.(`/ui/views/${view.id}`, view.component_name);
  }

  // ── Render ────────────────────────────────────────────────────────────────

  const actionButtons = (
    <>
      {/* Tools menu */}
      <Tooltip title="Insert tool mention">
        <Button
          size="small"
          startIcon={<TerminalIcon fontSize="small" />}
          onClick={openToolsMenu}
          sx={{ textTransform: "none", fontSize: "0.75rem", px: 1 }}
          variant="outlined"
          color="inherit"
        >
          Tools
        </Button>
      </Tooltip>
      <Menu
        anchorEl={toolsAnchor}
        open={Boolean(toolsAnchor)}
        onClose={() => setToolsAnchor(null)}
        slotProps={{ paper: { sx: { minWidth: 200 } } }}
      >
        {toolList.length === 0 ? (
          <MenuItem disabled>No tools available</MenuItem>
        ) : (
          toolList.map((t) => (
            <MenuItem key={t.name} onClick={() => selectTool(t.name)}>
              <Box>
                <Typography variant="body2">{t.name}</Typography>
                <Typography variant="caption" color="text.secondary">{t.description}</Typography>
              </Box>
            </MenuItem>
          ))
        )}
        <Divider />
        <MenuItem onClick={() => { setToolsAnchor(null); onOpenPanel?.("tools"); }}>
          <Typography variant="caption" color="primary">Open Tools panel →</Typography>
        </MenuItem>
      </Menu>

      {/* Components menu */}
      <Tooltip title="Insert component context">
        <Button
          size="small"
          startIcon={<CodeIcon fontSize="small" />}
          onClick={openCompsMenu}
          sx={{ textTransform: "none", fontSize: "0.75rem", px: 1 }}
          variant="outlined"
          color="inherit"
        >
          Components
        </Button>
      </Tooltip>
      <Menu
        anchorEl={compsAnchor}
        open={Boolean(compsAnchor)}
        onClose={() => setCompsAnchor(null)}
        slotProps={{ paper: { sx: { minWidth: 220 } } }}
      >
        {compList.length === 0 ? (
          <MenuItem disabled>No components yet</MenuItem>
        ) : (
          compList.map((c) => (
            <MenuItem key={c.id} onClick={() => selectComponent(c.id, c.name)}>
              <Box>
                <Typography variant="body2">{c.name}</Typography>
                <Typography variant="caption" color="text.secondary">{c.module_type}</Typography>
              </Box>
            </MenuItem>
          ))
        )}
        <Divider />
        <MenuItem onClick={() => { setCompsAnchor(null); onOpenPanel?.("dspy"); }}>
          <Typography variant="caption" color="primary">Open Components panel →</Typography>
        </MenuItem>
      </Menu>

      {/* New View button */}
      <Tooltip title="Generate a React view stub with AI">
        <Button
          size="small"
          startIcon={<WebIcon fontSize="small" />}
          onClick={() => setViewDialogOpen(true)}
          sx={{ textTransform: "none", fontSize: "0.75rem", px: 1 }}
          variant="outlined"
          color="primary"
        >
          New View
        </Button>
      </Tooltip>

      {/* Open Pipelines panel shortcut */}
      <Tooltip title="View pipelines">
        <IconButton size="small" onClick={() => onOpenPanel?.("pipelines")} sx={{ color: "text.secondary" }}>
          <AccountTreeIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      {/* Open Agent Runs panel shortcut */}
      <Tooltip title="Agent runs">
        <IconButton size="small" onClick={() => onOpenPanel?.("agents")} sx={{ color: "text.secondary" }}>
          <SmartToyIcon fontSize="small" />
        </IconButton>
      </Tooltip>
    </>
  );

  return (
    <Box sx={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Session sidebar */}
      <Box
        sx={{
          width: 220,
          flexShrink: 0,
          borderRight: "1px solid",
          borderColor: "divider",
          display: "flex",
          flexDirection: "column",
          bgcolor: "background.paper",
        }}
      >
        <Box sx={{ p: 1.5, display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="subtitle2" sx={{ flexGrow: 1, fontWeight: 600 }}>
            Conversations
          </Typography>
          <Tooltip title="New chat">
            <IconButton size="small" onClick={newSession}>
              <AddIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        </Box>
        <Divider />
        <List dense sx={{ flexGrow: 1, overflow: "auto" }}>
          {sessions.map((s) => (
            <ListItem
              key={s.id}
              disablePadding
              secondaryAction={
                <IconButton
                  edge="end"
                  size="small"
                  onClick={(e) => removeSession(s.id, e)}
                  sx={{ opacity: 0.5, "&:hover": { opacity: 1 } }}
                >
                  <DeleteOutlineIcon fontSize="small" />
                </IconButton>
              }
            >
              <ListItemButton
                selected={activeId === s.id}
                onClick={() => loadMessages(s.id)}
                sx={{ borderRadius: 1, mx: 0.5 }}
              >
                <ListItemText
                  primary={s.title}
                  primaryTypographyProps={{ variant: "body2", noWrap: true }}
                />
              </ListItemButton>
            </ListItem>
          ))}
          {sessions.length === 0 && (
            <ListItem>
              <ListItemText
                primary="No conversations yet"
                primaryTypographyProps={{ variant: "caption", color: "text.secondary" }}
              />
            </ListItem>
          )}
        </List>
      </Box>

      {/* Chat area */}
      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {activeId ? (
          <>
            {/* Messages */}
            <Box sx={{ flexGrow: 1, overflow: "auto", p: 2, display: "flex", flexDirection: "column", gap: 2 }}>
              {messages.length === 0 && (
                <Box sx={{ textAlign: "center", mt: 8, color: "text.secondary" }}>
                  <SmartToyIcon sx={{ fontSize: 48, mb: 1, opacity: 0.4 }} />
                  <Typography variant="body2">
                    Ask me to create a DSPy component, pipeline, or React view — or just chat about AI!
                  </Typography>
                </Box>
              )}
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onViewComponent={
                    msg.meta?.saved_component_id
                      ? () => onOpenPanel?.("dspy", msg.meta.saved_component_id)
                      : undefined
                  }
                  onViewPipeline={
                    msg.meta?.saved_pipeline_id
                      ? () => onOpenPanel?.("pipelines", msg.meta.saved_pipeline_id)
                      : undefined
                  }
                  onOpenView={
                    msg.meta?.saved_view_id
                      ? () => onOpenPanel?.("view", msg.meta.saved_view_id)
                      : undefined
                  }
                />
              ))}
              {sending && (
                <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>
                  <Avatar sx={{ width: 28, height: 28, bgcolor: "primary.main" }}>
                    <SmartToyIcon sx={{ fontSize: 16 }} />
                  </Avatar>
                  <CircularProgress size={16} />
                </Box>
              )}
              <div ref={bottomRef} />
            </Box>

            {/* Composer */}
            <Box sx={{ p: 2, borderTop: "1px solid", borderColor: "divider" }}>
              {/* Mobile: collapse action buttons behind [+] toggle */}
              {isMobile ? (
                <>
                  <Box sx={{ display: "flex", gap: 1, mb: actionsExpanded ? 1 : 0 }}>
                    <IconButton
                      size="small"
                      onClick={() => setActionsExpanded((v) => !v)}
                      sx={{ color: "text.secondary" }}
                    >
                      {actionsExpanded ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                    </IconButton>
                  </Box>
                  <Collapse in={actionsExpanded}>
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mb: 1 }}>
                      {actionButtons}
                    </Box>
                  </Collapse>
                </>
              ) : (
                <Box sx={{ display: "flex", gap: 0.75, mb: 1, flexWrap: "wrap" }}>
                  {actionButtons}
                </Box>
              )}

              <Box sx={{ display: "flex", gap: 1 }}>
                <TextField
                  fullWidth
                  multiline
                  maxRows={4}
                  placeholder="Ask me anything, or use the buttons above to insert tool/component context…"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  size="small"
                  variant="outlined"
                />
                <Button
                  variant="contained"
                  onClick={send}
                  disabled={!input.trim() || sending}
                  sx={{ minWidth: 48, px: 0 }}
                >
                  <SendIcon fontSize="small" />
                </Button>
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                Shift+Enter for newline · Enter to send
              </Typography>
            </Box>
          </>
        ) : (
          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%" }}>
            <Button variant="outlined" startIcon={<AddIcon />} onClick={newSession}>
              Start a new conversation
            </Button>
          </Box>
        )}
      </Box>

      {/* Generate View Dialog */}
      <GenerateViewDialog
        open={viewDialogOpen}
        sessionId={activeId}
        onClose={() => setViewDialogOpen(false)}
        onGenerated={handleViewGenerated}
      />
    </Box>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  message,
  onViewComponent,
  onViewPipeline,
  onOpenView,
}: {
  message: ChatMessage;
  onViewComponent?: () => void;
  onViewPipeline?: () => void;
  onOpenView?: () => void;
}) {
  const isUser = message.role === "user";

  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: isUser ? "row-reverse" : "row",
        gap: 1,
        alignItems: "flex-start",
      }}
    >
      <Avatar
        sx={{
          width: 28,
          height: 28,
          bgcolor: isUser ? "secondary.main" : "primary.main",
          flexShrink: 0,
        }}
      >
        {isUser ? "U" : <SmartToyIcon sx={{ fontSize: 16 }} />}
      </Avatar>

      <Paper
        elevation={0}
        sx={{
          maxWidth: "80%",
          p: 1.5,
          bgcolor: isUser ? "primary.dark" : "background.paper",
          border: "1px solid",
          borderColor: isUser ? "primary.main" : "divider",
          borderRadius: 2,
        }}
      >
        <ReactMarkdown
          components={{
            code({ node, className, children, ...props }) {
              const match = /language-(\w+)/.exec(className || "");
              const isBlock = !!(match || (String(children).includes("\n")));
              return isBlock ? (
                <SyntaxHighlighter
                  style={vscDarkPlus as any}
                  language={match?.[1] ?? "python"}
                  PreTag="div"
                  customStyle={{ fontSize: "0.8rem", borderRadius: 4 }}
                >
                  {String(children).replace(/\n$/, "")}
                </SyntaxHighlighter>
              ) : (
                <code
                  style={{
                    background: "rgba(255,255,255,0.1)",
                    padding: "2px 6px",
                    borderRadius: 3,
                    fontSize: "0.85em",
                  }}
                  {...props}
                >
                  {children}
                </code>
              );
            },
            p({ children }) {
              return (
                <Typography variant="body2" sx={{ mb: 0.5, lineHeight: 1.6 }}>
                  {children}
                </Typography>
              );
            },
          }}
        >
          {message.content}
        </ReactMarkdown>

        {/* Artifact chips */}
        {(message.meta?.saved_component_id || message.meta?.saved_pipeline_id || message.meta?.saved_view_id) && (
          <Box sx={{ mt: 1, display: "flex", flexWrap: "wrap", gap: 0.75 }}>
            {message.meta?.saved_component_id && (
              <Chip
                label="Component saved"
                size="small"
                color="success"
                variant="outlined"
                onClick={onViewComponent}
                clickable={!!onViewComponent}
                sx={{ fontSize: "0.7rem" }}
              />
            )}
            {message.meta?.saved_pipeline_id && (
              <Chip
                label="Pipeline saved"
                size="small"
                color="info"
                variant="outlined"
                onClick={onViewPipeline}
                clickable={!!onViewPipeline}
                sx={{ fontSize: "0.7rem" }}
              />
            )}
            {message.meta?.saved_view_id && (
              <Chip
                icon={<WebIcon sx={{ fontSize: "14px !important" }} />}
                label="→ Open View"
                size="small"
                color="secondary"
                variant="outlined"
                onClick={onOpenView}
                clickable={!!onOpenView}
                sx={{ fontSize: "0.7rem" }}
              />
            )}
          </Box>
        )}
      </Paper>
    </Box>
  );
}
