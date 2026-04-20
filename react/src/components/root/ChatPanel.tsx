/**
 * ChatPanel — root chat interface for interacting with DSPy components.
 *
 * Features:
 *  • Session list in a drawer-style sidebar
 *  • Message thread with markdown rendering and code block highlighting
 *  • Auto-saves AI-generated component/pipeline definitions
 *  • "View Component" quick-link when the AI creates a component
 */

import AddIcon from "@mui/icons-material/Add";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import SendIcon from "@mui/icons-material/Send";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import {
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import * as api from "./api";
import type { ChatMessage, ChatSession } from "./types";

interface Props {
  onComponentSaved?: (id: string) => void;
  onNavigate?: (tab: string) => void;
}

export default function ChatPanel({ onComponentSaved, onNavigate }: Props) {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Load sessions on mount ────────────────────────────────────────────────

  useEffect(() => {
    api.listSessions().then((s) => {
      setSessions(s);
      if (s.length > 0) loadMessages(s[0].id);
    });
  }, []);

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

    // Optimistic user bubble
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
      const reply = await api.sendMessage(activeId, userContent);
      // Replace optimistic message with server response messages
      const msgs = await api.listMessages(activeId);
      setMessages(msgs);

      if (reply.saved_component_id) {
        onComponentSaved?.(reply.saved_component_id);
      }
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

  // ── Render ────────────────────────────────────────────────────────────────

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
                    Ask me to create a DSPy component or pipeline, or just chat about AI!
                  </Typography>
                </Box>
              )}
              {messages.map((msg) => (
                <MessageBubble
                  key={msg.id}
                  message={msg}
                  onViewComponent={
                    msg.meta?.saved_component_id
                      ? () => onNavigate?.("dspy")
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

            {/* Input */}
            <Box sx={{ p: 2, borderTop: "1px solid", borderColor: "divider" }}>
              <Box sx={{ display: "flex", gap: 1 }}>
                <TextField
                  fullWidth
                  multiline
                  maxRows={4}
                  placeholder="Ask me to create a DSPy component, explain a pipeline, or help debug…"
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
    </Box>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  message,
  onViewComponent,
}: {
  message: ChatMessage;
  onViewComponent?: () => void;
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

        {/* Component saved chip */}
        {message.meta?.saved_component_id && (
          <Box sx={{ mt: 1 }}>
            <Chip
              label="Component saved"
              size="small"
              color="success"
              variant="outlined"
              onClick={onViewComponent}
              clickable={!!onViewComponent}
              sx={{ fontSize: "0.7rem" }}
            />
          </Box>
        )}
        {message.meta?.saved_pipeline_id && (
          <Box sx={{ mt: 1 }}>
            <Chip
              label="Pipeline saved"
              size="small"
              color="info"
              variant="outlined"
              sx={{ fontSize: "0.7rem" }}
            />
          </Box>
        )}
      </Paper>
    </Box>
  );
}
