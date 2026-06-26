import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  chatWithAgent,
  getErrorMessage,
  type AgentConfig,
  type ChatMessage,
  type ProviderConfig,
} from "../lib/api";
import {
  EmptyState,
  InlineNotice,
  PageHeader,
  Panel,
  StatusBadge,
  cx,
  formatRelativeTime,
} from "../components/ui";

interface ChatViewProps {
  agents: AgentConfig[];
  providers: ProviderConfig[];
  apiAvailable: boolean;
  warning: string | null;
}

export function ChatView({
  agents,
  providers,
  apiAvailable,
  warning,
}: ChatViewProps) {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [notice, setNotice] = useState<{
    tone: "good" | "warn" | "bad";
    title: string;
    description?: string;
  } | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === selectedAgentId) ?? agents[0] ?? null,
    [agents, selectedAgentId],
  );

  const providerMap = useMemo(
    () => new Map(providers.map((provider) => [provider.id, provider])),
    [providers],
  );

  useEffect(() => {
    if (agents.length > 0 && (!selectedAgentId || !agents.some((a) => a.id === selectedAgentId))) {
      setSelectedAgentId(agents[0].id);
    }
  }, [agents, selectedAgentId]);

  useEffect(() => {
    if (selectedAgent) {
      setMessages([
        {
          role: "system",
          content: selectedAgent.instructions,
          timestamp: undefined,
        },
      ]);
      setNotice(null);
    }
  }, [selectedAgent]);

  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  async function handleSend() {
    const trimmed = draft.trim();
    if (!trimmed || !selectedAgent || isStreaming) {
      return;
    }

    if (!apiAvailable) {
      setNotice({
        tone: "warn",
        title: "Chat APIs unavailable",
        description:
          "This Control Plane build does not expose the invocation routes yet.",
      });
      return;
    }

    const userMessage: ChatMessage = {
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };

    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    setDraft("");
    setIsStreaming(true);
    setNotice(null);

    try {
      const result = await chatWithAgent(selectedAgent.id, updatedMessages);
      setMessages((current) => [...current, result.message]);
    } catch (error) {
      setNotice({
        tone: "bad",
        title: "Failed to get response",
        description: getErrorMessage(error),
      });
    } finally {
      setIsStreaming(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void handleSend();
    }
  }

  function handleClearChat() {
    if (selectedAgent) {
      setMessages([
        {
          role: "system",
          content: selectedAgent.instructions,
          timestamp: undefined,
        },
      ]);
    } else {
      setMessages([]);
    }
    setNotice(null);
  }

  const userAssistantMessages = messages.filter(
    (m) => m.role === "user" || m.role === "assistant",
  );
  const canSend = Boolean(selectedAgent) && !isStreaming && draft.trim().length > 0;

  return (
    <div className="page-stack">
      <PageHeader
        title="Chat"
        description="Chat conversationally with an agent. The agent's instructions serve as the system prompt and conversation history builds context across turns."
        actions={
          <div className="button-row">
            <button
              className="button button--secondary"
              type="button"
              onClick={handleClearChat}
              disabled={isStreaming || messages.length <= 1}
            >
              Clear chat
            </button>
          </div>
        }
      />

      {warning ? (
        <InlineNotice
          tone={apiAvailable ? "warn" : "bad"}
          title={
            apiAvailable
              ? "Bootstrap fallback in use"
              : "Chat APIs unavailable"
          }
        >
          <p>{warning}</p>
        </InlineNotice>
      ) : null}

      {!selectedAgent ? (
        <EmptyState
          title="No agent available"
          description="Create and save an agent first, then return here to start a conversation."
        />
      ) : (
        <>
          {notice ? (
            <InlineNotice tone={notice.tone} title={notice.title}>
              {notice.description ? <p>{notice.description}</p> : null}
            </InlineNotice>
          ) : null}

          <div className="page-grid page-grid--playground">
            <div className="chat-container">
              <div className="chat-toolbar">
                <label className="field">
                  <span className="field__label">Agent</span>
                  <select
                    className="select"
                    value={selectedAgent.id}
                    onChange={(event) => setSelectedAgentId(event.target.value)}
                  >
                    {agents.map((agent) => (
                      <option key={agent.id} value={agent.id}>
                        {agent.name}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="hint-card">
                  <strong>{selectedAgent.name}</strong>
                  <p>
                    {selectedAgent.description || "No description provided."}
                  </p>
                  <div className="hint-card__meta">
                    <span>
                      Provider:{" "}
                      {providerMap.get(selectedAgent.defaultProviderId)?.name ??
                        "Missing provider"}
                    </span>
                    <span>Output: {selectedAgent.outputMode}</span>
                    <span>Reasoning: {selectedAgent.reasoningMode}</span>
                  </div>
                </div>
              </div>

              <Panel title="Conversation" subtitle="Your chat with the selected agent.">
                <div className="chat-message-list">
                  {userAssistantMessages.length === 0 ? (
                    <div className="chat-empty-hint">
                      <p>
                        The agent's instructions are loaded as the system
                        prompt. Type a message below to begin the conversation.
                      </p>
                    </div>
                  ) : (
                    userAssistantMessages.map((message, index) => (
                      <div
                        key={index}
                        className={cx(
                          "chat-message",
                          message.role === "user"
                            ? "chat-message--user"
                            : "chat-message--assistant",
                        )}
                      >
                        <div className="chat-message__sender">
                          {message.role === "user" ? "You" : selectedAgent.name}
                        </div>
                        <div className="chat-message__content">
                          {message.content}
                        </div>
                        {message.timestamp ? (
                          <div className="chat-message__time">
                            {formatRelativeTime(message.timestamp)}
                          </div>
                        ) : null}
                      </div>
                    ))
                  )}

                  {isStreaming ? (
                    <div className="chat-message chat-message--assistant">
                      <div className="chat-message__sender">
                        {selectedAgent.name}
                      </div>
                      <div className="chat-message__content chat-typing">
                        <span className="chat-typing__dot" />
                        <span className="chat-typing__dot" />
                        <span className="chat-typing__dot" />
                      </div>
                    </div>
                  ) : null}

                  {userAssistantMessages.length > 0 &&
                  !isStreaming &&
                  !notice ? (
                    <div className="chat-status-row">
                      <StatusBadge
                        tone="accent"
                        label="Ready"
                      />
                      <span className="muted-text">
                        {userAssistantMessages.length} message
                        {userAssistantMessages.length !== 1 ? "s" : ""}
                      </span>
                    </div>
                  ) : null}

                  <div ref={chatEndRef} />
                </div>
              </Panel>
            </div>

            <div className="chat-input-area">
              <Panel title="Send a message" subtitle="Press Enter to send, Shift+Enter for a new line.">
                <label className="field">
                  <textarea
                    className="textarea textarea--lg"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Type your message…"
                    disabled={isStreaming}
                    aria-label="Chat message"
                  />
                </label>

                <div className="editor-footer">
                  <div className="editor-footer__meta">
                    <StatusBadge
                      status={selectedAgent.enabled ? "enabled" : "disabled"}
                      label={
                        selectedAgent.enabled ? "Enabled" : "Disabled"
                      }
                    />
                    <span>
                      Default provider{" "}
                      {providerMap.get(selectedAgent.defaultProviderId)?.name ??
                        "missing"}
                    </span>
                  </div>
                  <div className="button-row">
                    <button
                      className="button button--primary"
                      type="button"
                      onClick={() => {
                        void handleSend();
                      }}
                      disabled={!canSend}
                    >
                      {isStreaming ? "Waiting…" : "Send"}
                    </button>
                  </div>
                </div>
              </Panel>

              <details className="details-block">
                <summary>Agent instructions (system prompt)</summary>
                <pre className="code-block code-block--wrap">
                  {selectedAgent.instructions || "No instructions set."}
                </pre>
              </details>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
