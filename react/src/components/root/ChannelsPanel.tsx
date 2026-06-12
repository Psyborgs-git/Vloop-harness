/**
 * ChannelsPanel — self-contained Hexagonal Chat Channels UI.
 * Handles user authentication (Login/Register) and real-time multi-user channel chats.
 */

import AddIcon from "@mui/icons-material/Add";
import LockIcon from "@mui/icons-material/Lock";
import LogoutIcon from "@mui/icons-material/Logout";
import PersonIcon from "@mui/icons-material/Person";
import PublicIcon from "@mui/icons-material/Public";
import SendIcon from "@mui/icons-material/Send";
import SmartToyIcon from "@mui/icons-material/SmartToy";
import TelegramIcon from "@mui/icons-material/Telegram";
import {
  Avatar,
  Box,
  Checkbox,
  Divider,
  FormControlLabel,
  IconButton,
  List,
  ListItemButton,
  Paper,
  Typography,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";

import * as api from "./api";
import type { ChannelType, ChannelMessageType } from "./api";
import Button from "../ui/Button";
import Input from "../ui/Input";
import Card from "../ui/Card";
import Dialog from "../ui/Dialog";

export default function ChannelsPanel() {
  const [token, setToken] = useState<string | null>(api.getAuthToken());
  const [currentUser, setCurrentUser] = useState<any | null>(null);
  
  // Auth Form State
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");

  // Chat/Channel States
  const [channels, setChannels] = useState<ChannelType[]>([]);
  const [activeChannel, setActiveChannel] = useState<ChannelType | null>(null);
  const [messages, setMessages] = useState<ChannelMessageType[]>([]);
  const [inputText, setInputText] = useState("");
  const [ws, setWs] = useState<WebSocket | null>(null);

  // Dialog State
  const [createOpen, setCreateOpen] = useState(false);
  const [newChanName, setNewChanName] = useState("");
  const [newChanDesc, setNewChanDesc] = useState("");
  const [newChanPrivate, setNewChanPrivate] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // ── Auth Effects ───────────────────────────────────────────────────────────

  useEffect(() => {
    if (token) {
      api.getMe()
        .then((user) => {
          setCurrentUser(user);
          loadChannels();
        })
        .catch(() => {
          // Token expired or invalid
          handleLogout();
        });
    }
  }, [token]);

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthError("");
    try {
      if (isRegister) {
        await api.register({ username, password });
        // Auto-login after registration
        const res = await api.login({ username, password });
        api.setAuthToken(res.access_token);
        setToken(res.access_token);
      } else {
        const res = await api.login({ username, password });
        api.setAuthToken(res.access_token);
        setToken(res.access_token);
      }
      setUsername("");
      setPassword("");
    } catch (err: any) {
      setAuthError(err.message || "Authentication failed");
    }
  };

  const handleLogout = () => {
    api.setAuthToken(null);
    setToken(null);
    setCurrentUser(null);
    setChannels([]);
    setActiveChannel(null);
    setMessages([]);
    if (ws) {
      ws.close();
      setWs(null);
    }
  };

  // ── Channels Logic ─────────────────────────────────────────────────────────

  const loadChannels = async () => {
    try {
      const list = await api.listChannels();
      setChannels(list);
      // Auto-select first channel if none is selected
      if (list.length > 0 && !activeChannel) {
        selectChannel(list[0]);
      }
    } catch (err) {
      console.error("Failed to load channels:", err);
    }
  };

  const selectChannel = async (channel: ChannelType) => {
    setActiveChannel(channel);
    
    // Close existing WebSocket
    if (ws) {
      ws.close();
    }

    try {
      // 1. Fetch channel history
      const history = await api.listChannelMessages(channel.id);
      setMessages(history);

      // 2. Connect to real-time WebSockets
      const rawApiUrl = (window as any).__HARNESS__?.API_URL ?? "http://localhost:9100";
      const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
      const wsHost = rawApiUrl.replace(/^https?:\/\//, "").replace(/\/api\/.*/, "");
      const wsUrl = `${wsProtocol}://${wsHost}/api/channels/ws/${channel.id}?token=${token}`;

      const socket = new WebSocket(wsUrl);

      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === "message_created") {
            const newMsg = payload.data as ChannelMessageType;
            // Append message only if it belongs to active channel
            if (newMsg.channel_id === channel.id) {
              setMessages((prev) => {
                // Avoid double appending
                if (prev.some((m) => m.id === newMsg.id)) return prev;
                return [...prev, newMsg];
              });
            }
          }
        } catch (e) {
          console.error("Error parsing WebSocket message:", e);
        }
      };

      socket.onclose = () => {
        console.log("WebSocket disconnected");
      };

      setWs(socket);
    } catch (err) {
      console.error("Error entering channel:", err);
    }
  };

  const handleCreateChannel = async () => {
    if (!newChanName.trim()) return;
    try {
      const chan = await api.createChannel({
        name: newChanName.trim(),
        description: newChanDesc.trim(),
        is_private: newChanPrivate,
      });
      setChannels((prev) => [...prev, chan]);
      selectChannel(chan);
      setCreateOpen(false);
      setNewChanName("");
      setNewChanDesc("");
      setNewChanPrivate(false);
    } catch (err: any) {
      alert(err.message || "Failed to create channel");
    }
  };

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim() || !activeChannel) return;

    try {
      await api.sendChannelMessage(activeChannel.id, inputText.trim());
      setInputText("");
    } catch (err) {
      console.error("Error sending message:", err);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Clean up WS on unmount
  useEffect(() => {
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [ws]);

  // ── Render Login Wall ──────────────────────────────────────────────────────

  if (!currentUser) {
    return (
      <Box
        sx={{
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          height: "100%",
          bgcolor: "background.default",
        }}
      >
        <Card sx={{ width: 400, p: 4 }}>
          <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", mb: 3 }}>
            <SmartToyIcon sx={{ color: "primary.main", fontSize: 40, mb: 1 }} />
            <Typography variant="h5" fontWeight={600} fontFamily="Inter, sans-serif" sx={{ letterSpacing: "-0.01em" }}>
              {isRegister ? "Join VLoop Workspace" : "Welcome Back"}
            </Typography>
            <Typography variant="caption" color="text.secondary" fontFamily="Inter, sans-serif" sx={{ mt: 0.5 }}>
              Sign in to participate in the Chat Channels
            </Typography>
          </Box>

          <form onSubmit={handleAuth}>
            <Input
              label="Username"
              fullWidth
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              sx={{ mb: 2 }}
            />
            <Input
              label="Password"
              type="password"
              fullWidth
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              sx={{ mb: 2 }}
            />

            {authError && (
              <Typography color="error" variant="caption" fontFamily="Inter, sans-serif" sx={{ mt: 1, display: "block" }}>
                {authError}
              </Typography>
            )}

            <Button
              type="submit"
              variant="contained"
              colorType="primary"
              fullWidth
              sx={{ mt: 2, mb: 2 }}
            >
              {isRegister ? "Register" : "Login"}
            </Button>
          </form>

          <Divider sx={{ my: 2, borderColor: "rgba(255,255,255,0.08)" }} />

          <Box sx={{ textAlign: "center" }}>
            <Button
              variant="text"
              colorType="neutral"
              size="small"
              onClick={() => setIsRegister(!isRegister)}
            >
              {isRegister ? "Already have an account? Sign In" : "New to VLoop? Create Account"}
            </Button>
          </Box>
        </Card>
      </Box>
    );
  }

  // ── Render Channel Interface ───────────────────────────────────────────────

  return (
    <Box sx={{ display: "flex", height: "100%", bgcolor: "background.default", overflow: "hidden" }}>
      
      {/* 1. Left Sidebar */}
      <Box
        sx={{
          width: 260,
          borderRight: "1px solid rgba(255,255,255,0.06)",
          display: "flex",
          flexDirection: "column",
          bgcolor: "#0f0f13",
        }}
      >
        {/* Header */}
        <Box
          sx={{
            p: 2,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            borderBottom: "1px solid rgba(255,255,255,0.04)",
          }}
        >
          <Typography
            variant="caption"
            fontWeight={600}
            color="text.secondary"
            fontFamily="Inter, sans-serif"
            sx={{ letterSpacing: "0.08em" }}
          >
            CHANNELS
          </Typography>
          <IconButton
            size="small"
            onClick={() => setCreateOpen(true)}
            sx={{
              color: "text.secondary",
              borderRadius: "4px",
              "&:hover": { color: "text.primary", bgcolor: "rgba(255,255,255,0.04)" },
            }}
          >
            <AddIcon fontSize="small" />
          </IconButton>
        </Box>

        {/* Channel List */}
        <Box sx={{ flexGrow: 1, overflowY: "auto", py: 1 }}>
          <List dense sx={{ p: 0 }}>
            {channels.map((chan) => {
              const isActive = activeChannel?.id === chan.id;
              const isTelegram = chan.name.startsWith("telegram_");
              
              // Formatting title
              let displayTitle = chan.name;
              if (isTelegram) {
                displayTitle = chan.description.replace("Bridged Telegram Channel: ", "Telegram: ");
              }

              return (
                <ListItemButton
                  key={chan.id}
                  onClick={() => selectChannel(chan)}
                  selected={isActive}
                  sx={{
                    py: 0.75,
                    px: 2,
                    mx: 1,
                    my: 0.25,
                    borderRadius: "8px",
                    bgcolor: isActive ? "rgba(99,102,241,0.08)" : "transparent",
                    border: isActive ? "1px solid rgba(99,102,241,0.15)" : "1px solid transparent",
                    "&.Mui-selected": {
                      bgcolor: "rgba(99,102,241,0.08)",
                      border: "1px solid rgba(99,102,241,0.15)",
                      "&:hover": { bgcolor: "rgba(99,102,241,0.12)" },
                    },
                    "&:hover": {
                      bgcolor: "rgba(255,255,255,0.02)",
                    },
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
                    {isTelegram ? (
                      <TelegramIcon sx={{ fontSize: 16, color: "#229ED9" }} />
                    ) : chan.is_private ? (
                      <LockIcon sx={{ fontSize: 16, color: "text.secondary" }} />
                    ) : (
                      <PublicIcon sx={{ fontSize: 16, color: isActive ? "primary.main" : "text.secondary" }} />
                    )}
                    <Typography
                      variant="body2"
                      fontWeight={isActive ? 600 : 400}
                      fontFamily="Inter, sans-serif"
                      sx={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        color: isActive ? "text.primary" : "text.secondary",
                      }}
                    >
                      {isTelegram ? displayTitle : `# ${displayTitle}`}
                    </Typography>
                  </Box>
                </ListItemButton>
              );
            })}
          </List>
        </Box>

        {/* User Footer */}
        <Box sx={{ p: 2, borderTop: "1px solid rgba(255,255,255,0.06)", bgcolor: "#13131a" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
            <Avatar sx={{ width: 28, height: 28, bgcolor: "primary.main" }}>
              <PersonIcon sx={{ fontSize: 16 }} />
            </Avatar>
            <Box sx={{ overflow: "hidden" }}>
              <Typography variant="caption" fontWeight={600} fontFamily="Inter, sans-serif" sx={{ display: "block" }}>
                {currentUser.username}
              </Typography>
              <Typography variant="caption" color="text.secondary" fontFamily="Inter, sans-serif" sx={{ textTransform: "capitalize", fontSize: "0.7rem" }}>
                {currentUser.role}
              </Typography>
            </Box>
          </Box>
          <Button
            size="small"
            variant="text"
            colorType="neutral"
            fullWidth
            onClick={handleLogout}
            startIcon={<LogoutIcon sx={{ fontSize: 12 }} />}
            sx={{
              justifyContent: "flex-start",
              fontSize: "0.75rem",
              py: 0.5,
            }}
          >
            Logout
          </Button>
        </Box>
      </Box>

      {/* 2. Main Chat View */}
      <Box sx={{ flexGrow: 1, display: "flex", flexDirection: "column", height: "100%", bgcolor: "background.default" }}>
        {activeChannel ? (
          <>
            {/* Header */}
            <Box
              sx={{
                p: 2,
                borderBottom: "1px solid rgba(255,255,255,0.06)",
                bgcolor: "background.paper",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                {activeChannel.name.startsWith("telegram_") ? (
                  <TelegramIcon sx={{ color: "#229ED9" }} />
                ) : activeChannel.is_private ? (
                  <LockIcon sx={{ color: "text.secondary" }} />
                ) : (
                  <PublicIcon sx={{ color: "primary.main" }} />
                )}
                <Typography variant="subtitle1" fontWeight={600} fontFamily="Inter, sans-serif" sx={{ letterSpacing: "-0.01em" }}>
                  {activeChannel.name.startsWith("telegram_")
                    ? activeChannel.description.replace("Bridged Telegram Channel: ", "")
                    : activeChannel.name}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary" fontFamily="Inter, sans-serif" sx={{ mt: 0.5 }}>
                {activeChannel.description || "No description provided"}
              </Typography>
            </Box>

            {/* Message Thread */}
            <Box sx={{ flexGrow: 1, overflowY: "auto", p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
              {messages.length === 0 ? (
                <Box
                  sx={{
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                    height: "100%",
                    color: "text.secondary",
                  }}
                >
                  <Typography variant="body2" fontFamily="Inter, sans-serif">No messages in this channel yet.</Typography>
                </Box>
              ) : (
                messages.map((msg) => {
                  const isAi = msg.sender_type === "ai";
                  const isTelegram = msg.sender_type === "telegram";
                  return (
                    <Box key={msg.id} sx={{ display: "flex", gap: 1.5 }}>
                      <Avatar
                        sx={{
                          width: 32,
                          height: 32,
                          bgcolor: isAi ? "secondary.main" : isTelegram ? "#229ED9" : "primary.main",
                        }}
                      >
                        {isAi ? (
                          <SmartToyIcon sx={{ fontSize: 18 }} />
                        ) : isTelegram ? (
                          <TelegramIcon sx={{ fontSize: 18 }} />
                        ) : (
                          <PersonIcon sx={{ fontSize: 18 }} />
                        )}
                      </Avatar>
                      <Box sx={{ flexGrow: 1 }}>
                        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                          <Typography variant="subtitle2" fontWeight={600} fontFamily="Inter, sans-serif">
                            {msg.sender_name}
                          </Typography>
                          {isAi && (
                            <Typography
                              variant="caption"
                              fontWeight={600}
                              fontFamily="Inter, sans-serif"
                              sx={{
                                px: 1,
                                py: 0.1,
                                borderRadius: "4px",
                                bgcolor: "secondary.main",
                                color: "white",
                                fontSize: "0.6rem",
                              }}
                            >
                              BOT
                            </Typography>
                          )}
                          {isTelegram && (
                            <Typography
                              variant="caption"
                              fontWeight={600}
                              fontFamily="Inter, sans-serif"
                              sx={{
                                px: 1,
                                py: 0.1,
                                borderRadius: "4px",
                                bgcolor: "#229ED9",
                                color: "white",
                                fontSize: "0.6rem",
                              }}
                            >
                              TELEGRAM
                            </Typography>
                          )}
                          <Typography variant="caption" color="text.secondary" fontFamily="Inter, sans-serif">
                            {new Date(msg.created_at).toLocaleTimeString([], {
                              hour: "2-digit",
                              minute: "2-digit",
                            })}
                          </Typography>
                        </Box>
                        
                        <Paper
                          sx={{
                            p: 1.5,
                            bgcolor: isAi ? "rgba(236,72,153,0.03)" : "#13131a",
                            border: isAi ? "1px solid rgba(236,72,153,0.15)" : "1px solid rgba(255,255,255,0.06)",
                            borderRadius: "8px",
                            boxShadow: "none",
                            display: "inline-block",
                            maxWidth: "85%",
                          }}
                        >
                          <Typography variant="body2" sx={{ "& p": { m: 0 }, fontFamily: "Inter, sans-serif", lineHeight: 1.5, color: "text.primary" }}>
                            <ReactMarkdown>{msg.content}</ReactMarkdown>
                          </Typography>
                        </Paper>
                      </Box>
                    </Box>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </Box>

            {/* Composer */}
            <Box sx={{ p: 2, bgcolor: "background.paper", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <form onSubmit={handleSendMessage}>
                <Box sx={{ display: "flex", gap: 1 }}>
                  <Input
                    placeholder={`Message #${activeChannel.name}`}
                    fullWidth
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    autoComplete="off"
                  />
                  <IconButton
                    type="submit"
                    color="primary"
                    disabled={!inputText.trim()}
                    sx={{
                      borderRadius: "8px",
                      color: "primary.main",
                      "&.Mui-disabled": { color: "text.disabled" },
                      "&:hover": { bgcolor: "rgba(99,102,241,0.08)" },
                    }}
                  >
                    <SendIcon />
                  </IconButton>
                </Box>
              </form>
            </Box>
          </>
        ) : (
          <Box
            sx={{
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              height: "100%",
              color: "text.secondary",
            }}
          >
            <Typography variant="body1" fontFamily="Inter, sans-serif">Select or create a channel to start talking.</Typography>
          </Box>
        )}
      </Box>

      {/* ── Dialog: Create Channel ────────────────────────────────────────────── */}
      <Dialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        maxWidth="xs"
        fullWidth
        titleText="Create Channel"
        actions={
          <>
            <Button
              onClick={() => setCreateOpen(false)}
              size="small"
              variant="text"
              colorType="neutral"
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateChannel}
              variant="contained"
              colorType="primary"
              size="small"
            >
              Create
            </Button>
          </>
        }
      >
        <Input
          label="Name"
          fullWidth
          value={newChanName}
          onChange={(e) => setNewChanName(e.target.value.toLowerCase().replace(/\s+/g, "-"))}
          helperText="Lowercase, no spaces"
          required
          sx={{ mb: 2 }}
        />
        <Input
          label="Description"
          fullWidth
          value={newChanDesc}
          onChange={(e) => setNewChanDesc(e.target.value)}
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={newChanPrivate}
              onChange={(e) => setNewChanPrivate(e.target.checked)}
              sx={{
                color: "rgba(255,255,255,0.2)",
                "&.Mui-checked": { color: "primary.main" },
              }}
            />
          }
          label="Make Private"
          sx={{ mt: 2, "& .MuiFormControlLabel-label": { fontFamily: "Inter, sans-serif", fontSize: "0.875rem", color: "text.secondary" } }}
        />
      </Dialog>

    </Box>
  );
}
