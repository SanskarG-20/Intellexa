import { SignOutButton, useUser } from "@clerk/clerk-react";
import { useCallback, useEffect, useRef, useState } from "react";
import ChatHistorySidebar from "../components/ChatHistorySidebar";
import { useApiService } from "../services/apiService";
import { getChatById, getUserChats, saveMessage } from "../services/chatHistory";

const PERSPECTIVE_TABS = [
  { key: "utilitarian", label: "Utilitarian" },
  { key: "rights_based", label: "Rights-based" },
  { key: "care_ethics", label: "Care ethics" },
];

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function formatLabel(key) {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "N/A";
  }

  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(", ");
  }

  if (isPlainObject(value)) {
    return JSON.stringify(value);
  }

  return String(value);
}

function extractMainAnswer(data) {
  if (typeof data?.response === "string" && data.response.trim()) {
    return data.response.trim();
  }

  if (typeof data?.answer === "string" && data.answer.trim()) {
    return data.answer.trim();
  }

  if (!isPlainObject(data?.answer)) {
    return "";
  }

  const answerObject = data.answer;
  const priorityKeys = ["main", "content", "summary", "utilitarian", "rights_based", "care_ethics"];

  for (const key of priorityKeys) {
    if (typeof answerObject[key] === "string" && answerObject[key].trim()) {
      return answerObject[key].trim();
    }
  }

  const firstTextEntry = Object.values(answerObject).find(
    (value) => typeof value === "string" && value.trim()
  );

  return firstTextEntry ? firstTextEntry.trim() : "";
}

function extractExplanationItems(data) {
  if (Array.isArray(data?.explanation)) {
    return data.explanation
      .map((item) => String(item).trim())
      .filter(Boolean);
  }

  if (typeof data?.explanation === "string" && data.explanation.trim()) {
    return data.explanation
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  return [];
}

function extractAutopsyPayload(data) {
  if (!isPlainObject(data?.perspective_autopsy)) {
    return null;
  }

  const source = data.perspective_autopsy;
  const assumptions = Array.isArray(source.assumptions)
    ? source.assumptions.map((item) => String(item).trim()).filter(Boolean)
    : [];
  const missingAngles = Array.isArray(source.missing_angles)
    ? source.missing_angles.map((item) => String(item).trim()).filter(Boolean)
    : [];
  const biasDetected = String(source.bias_detected ?? "none").trim() || "none";

  return {
    assumptions,
    biasDetected,
    missingAngles,
  };
}

function extractPerspectivePayload(data) {
  const source = isPlainObject(data?.answer)
    ? data.answer
    : isPlainObject(data?.ethical_perspectives)
      ? data.ethical_perspectives
      : null;

  if (!source) {
    return null;
  }

  const perspectives = {
    utilitarian: String(source.utilitarian ?? "").trim(),
    rights_based: String(source.rights_based ?? "").trim(),
    care_ethics: String(source.care_ethics ?? "").trim(),
  };

  if (!Object.values(perspectives).some(Boolean)) {
    return null;
  }

  return perspectives;
}

function buildStructuredPayload(data) {
  const explanationItems = extractExplanationItems(data);
  const autopsy = extractAutopsyPayload(data);
  const perspectives = extractPerspectivePayload(data);
  const ethicalCheck = isPlainObject(data?.ethical_check)
    ? data.ethical_check
    : isPlainObject(data?.audit_results)
      ? data.audit_results
      : null;
  const trustScore = data?.trust_score ?? null;
  const confidence = data?.confidence ?? null;

  return {
    autopsy,
    perspectives,
    answer: extractMainAnswer(data),
    explanationItems,
    ethicalCheck,
    trustScore,
    confidence,
  };
}

function PerspectiveTabs({ perspectives }) {
  const availableTabs = PERSPECTIVE_TABS.filter((tab) => {
    const value = perspectives?.[tab.key];
    return typeof value === "string" && value.trim();
  });

  const [activeTab, setActiveTab] = useState(availableTabs[0]?.key || "utilitarian");

  useEffect(() => {
    const isActiveTabAvailable = availableTabs.some((tab) => tab.key === activeTab);
    if (!isActiveTabAvailable && availableTabs.length) {
      setActiveTab(availableTabs[0].key);
    }
  }, [activeTab, availableTabs]);

  if (!availableTabs.length) {
    return null;
  }

  const activePerspective = perspectives?.[activeTab] || "";

  return (
    <section className="chat-structured-panel">
      <h3 className="chat-panel-title">Answer Perspectives</h3>
      <div className="chat-perspective-tabs" role="tablist" aria-label="Ethical perspectives">
        {availableTabs.map((tab) => {
          const isActive = tab.key === activeTab;

          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`chat-perspective-tab ${isActive ? "is-active" : ""}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <p className="chat-perspective-body">{activePerspective}</p>
    </section>
  );
}

function ExplanationPanel({ items }) {
  const hasItems = Array.isArray(items) && items.length > 0;
  const [isExpanded, setIsExpanded] = useState(false);

  if (!hasItems) {
    return null;
  }

  return (
    <section className="chat-structured-panel chat-explanation-panel">
      <button
        type="button"
        className="chat-explanation-toggle"
        onClick={() => setIsExpanded((value) => !value)}
        aria-expanded={isExpanded}
      >
        <span className="chat-panel-title chat-panel-title-inline">Why this answer?</span>
        <span className={`chat-explanation-chevron ${isExpanded ? "is-open" : ""}`} aria-hidden="true">
          ▾
        </span>
      </button>

      {isExpanded ? (
        <ul className="chat-panel-list chat-explanation-list">
          {items.map((item, index) => (
            <li key={`explanation-${index}`}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="chat-explanation-hint">Click to view explanation points.</p>
      )}
    </section>
  );
}

function createChatMessage(role, content, structured = null) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    structured,
  };
}

const WELCOME_MESSAGE =
  "Welcome to Intellexa. Ask a question and I will respond with context-aware reasoning.";

function buildMessagesFromSavedChat(chat) {
  const items = [];
  const question = String(chat?.message || "").trim();
  const answer = String(chat?.response || "").trim();

  if (question) {
    items.push(createChatMessage("user", question));
  }

  if (answer) {
    items.push(createChatMessage("assistant", answer));
  }

  if (!items.length) {
    items.push(createChatMessage("assistant", "This chat item has no saved content."));
  }

  return items;
}

function Dashboard() {
  const { user } = useUser();
  const { sendMessage } = useApiService();
  const userId = typeof user?.id === "string" ? user.id.trim() : "";
  const name =
    user?.firstName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    "Builder";
  const [messages, setMessages] = useState(() => [
    createChatMessage("assistant", WELCOME_MESSAGE),
  ]);
  const [chatHistoryItems, setChatHistoryItems] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [historyErrorMessage, setHistoryErrorMessage] = useState("");
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const historyRef = useRef(null);

  const loadHistory = useCallback(
    async (preferredChatId = null) => {
      if (!userId) {
        setChatHistoryItems([]);
        setActiveChatId(null);
        return;
      }

      setIsHistoryLoading(true);
      setHistoryErrorMessage("");

      try {
        const chats = await getUserChats(userId);
        setChatHistoryItems(chats);

        setActiveChatId((current) => {
          if (preferredChatId && chats.some((item) => item.id === preferredChatId)) {
            return preferredChatId;
          }

          if (current && chats.some((item) => item.id === current)) {
            return current;
          }

          return null;
        });
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Unable to load chat history right now.";
        setHistoryErrorMessage(message);
      } finally {
        setIsHistoryLoading(false);
      }
    },
    [userId]
  );

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    if (!historyRef.current) return;

    historyRef.current.scrollTo({
      top: historyRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isLoading]);

  const handleSelectHistoryItem = useCallback(async (chatId) => {
    if (!chatId) {
      return;
    }

    setHistoryErrorMessage("");
    setActiveChatId(chatId);

    try {
      const chat = await getChatById(chatId);

      if (!chat) {
        setMessages([createChatMessage("assistant", "Could not load this conversation.")]);
        return;
      }

      setMessages(buildMessagesFromSavedChat(chat));
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to load selected chat history.";
      setHistoryErrorMessage(message);
    }
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();

    const nextMessage = inputValue.trim();
    if (!nextMessage || isLoading) return;

    setErrorMessage("");
    setInputValue("");
    setMessages((prev) => [...prev, createChatMessage("user", nextMessage)]);
    setIsLoading(true);

    try {
      const data = await sendMessage(nextMessage);
      const structuredPayload = buildStructuredPayload(data);
      const aiText = structuredPayload.answer || "I could not generate a response just now.";

      setMessages((prev) => [
        ...prev,
        createChatMessage("assistant", aiText, structuredPayload),
      ]);

      if (userId) {
        try {
          const saved = await saveMessage(userId, nextMessage, aiText);
          await loadHistory(saved?.id || null);
        } catch (historyError) {
          const message =
            historyError instanceof Error
              ? historyError.message
              : "Failed to save chat history.";
          setHistoryErrorMessage(message);
        }
      }
    } catch (error) {
      const fallback = "Unable to reach Intellexa right now. Please try again.";
      const message = error instanceof Error ? error.message : fallback;
      const userVisibleMessage = message || fallback;

      setErrorMessage(userVisibleMessage);
      setMessages((prev) => [
        ...prev,
        createChatMessage(
          "assistant",
          `I hit an issue while processing that request: ${userVisibleMessage}`
        ),
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleInputKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!isLoading) {
        void handleSubmit(event);
      }
    }
  };

  return (
    <section className="dashboard-page">
      <div className="dashboard-card dashboard-chat-card">
        <header className="dashboard-header">
          <div>
            <p className="dashboard-kicker">INTELLEXA DASHBOARD</p>
            <h1 className="dashboard-title">Welcome, {name}</h1>
            <p className="dashboard-subtitle">Your authenticated AI chat workspace.</p>
          </div>
          <SignOutButton>
            <button className="dashboard-signout" type="button">
              Sign out
            </button>
          </SignOutButton>
        </header>

        {errorMessage ? (
          <p className="chat-error-banner" role="status">
            {errorMessage}
          </p>
        ) : null}

        <div className="dashboard-chat-layout">
          <ChatHistorySidebar
            chats={chatHistoryItems}
            activeChatId={activeChatId}
            isLoading={isHistoryLoading}
            errorMessage={historyErrorMessage}
            onSelectChat={handleSelectHistoryItem}
          />

          <div className="dashboard-chat-main">
            <div className="chat-history" ref={historyRef} aria-live="polite" aria-busy={isLoading}>
              {messages.map((message) => {
                const isAssistant = message.role === "assistant";
                const structured = message.structured;
                const hasAutopsy = Boolean(structured?.autopsy);
                const hasPerspectives = Boolean(
                  structured?.perspectives &&
                    Object.values(structured.perspectives).some(
                      (value) => typeof value === "string" && value.trim()
                    )
                );
                const hasExplanation = Boolean(structured?.explanationItems?.length);
                const hasEthicalCheck = Boolean(
                  structured?.ethicalCheck && Object.keys(structured.ethicalCheck).length
                );
                const hasTrustBlock =
                  (structured?.trustScore !== null && structured?.trustScore !== undefined) ||
                  (typeof structured?.confidence === "string" && structured.confidence.trim());
                const shouldRenderStructured =
                  isAssistant && (hasAutopsy || hasPerspectives || hasExplanation || hasEthicalCheck || hasTrustBlock);

                return (
                  <article
                    key={message.id}
                    className={`chat-message chat-message-${message.role}`}
                  >
                    <span className="chat-message-role">
                      {message.role === "user" ? "You" : "Intellexa"}
                    </span>

                    {shouldRenderStructured ? (
                      <div className="chat-structured">
                        {hasAutopsy ? (
                          <section className="chat-structured-panel chat-autopsy-panel">
                            <h3 className="chat-panel-title chat-autopsy-title">Perspective Autopsy</h3>
                            <p className="chat-autopsy-kicker">Before answer generation</p>

                            <div className="chat-autopsy-group">
                              <p className="chat-autopsy-label">Assumptions</p>
                              {structured.autopsy.assumptions.length ? (
                                <ul className="chat-panel-list">
                                  {structured.autopsy.assumptions.map((item, index) => (
                                    <li key={`${message.id}-autopsy-assumption-${index}`}>{item}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="chat-autopsy-empty">No assumptions detected.</p>
                              )}
                            </div>

                            <div className="chat-autopsy-group">
                              <p className="chat-autopsy-label">Bias Detected</p>
                              <p className="chat-autopsy-bias">{structured.autopsy.biasDetected || "none"}</p>
                            </div>

                            <div className="chat-autopsy-group">
                              <p className="chat-autopsy-label">Missing Angles</p>
                              {structured.autopsy.missingAngles.length ? (
                                <ul className="chat-panel-list">
                                  {structured.autopsy.missingAngles.map((item, index) => (
                                    <li key={`${message.id}-autopsy-angle-${index}`}>{item}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="chat-autopsy-empty">No missing angles identified.</p>
                              )}
                            </div>
                          </section>
                        ) : null}

                        {hasPerspectives ? (
                          <PerspectiveTabs perspectives={structured.perspectives} />
                        ) : (
                          <section className="chat-structured-panel">
                            <h3 className="chat-panel-title">Answer</h3>
                            <p>{structured.answer || message.content}</p>
                          </section>
                        )}

                        {hasExplanation ? <ExplanationPanel items={structured.explanationItems} /> : null}

                        {hasEthicalCheck ? (
                          <section className="chat-structured-panel">
                            <h3 className="chat-panel-title">Ethical Check</h3>
                            <div className="chat-meta-grid">
                              {Object.entries(structured.ethicalCheck).map(([key, value]) => (
                                <div key={`${message.id}-${key}`} className="chat-meta-item">
                                  <span className="chat-meta-label">{formatLabel(key)}</span>
                                  <span className="chat-meta-value">{formatValue(value)}</span>
                                </div>
                              ))}
                            </div>
                          </section>
                        ) : null}

                        {hasTrustBlock ? (
                          <section className="chat-structured-panel">
                            <h3 className="chat-panel-title">Trust</h3>
                            <div className="chat-meta-grid">
                              {structured.trustScore !== null && structured.trustScore !== undefined ? (
                                <div className="chat-meta-item">
                                  <span className="chat-meta-label">Trust Score</span>
                                  <span className="chat-meta-value">{formatValue(structured.trustScore)}</span>
                                </div>
                              ) : null}

                              {typeof structured.confidence === "string" && structured.confidence.trim() ? (
                                <div className="chat-meta-item">
                                  <span className="chat-meta-label">Confidence</span>
                                  <span className="chat-meta-value">{structured.confidence.trim()}</span>
                                </div>
                              ) : null}
                            </div>
                          </section>
                        ) : null}
                      </div>
                    ) : (
                      <p>{message.content}</p>
                    )}
                  </article>
                );
              })}

              {isLoading ? (
                <article className="chat-message chat-message-assistant chat-message-loading" aria-label="Intellexa is typing">
                  <span className="chat-message-role">Intellexa</span>
                  <div className="chat-typing-dots" aria-hidden="true">
                    <span />
                    <span />
                    <span />
                  </div>
                </article>
              ) : null}
            </div>

            <form className="chat-input-form" onSubmit={handleSubmit}>
              <label className="chat-input-label" htmlFor="dashboard-chat-input">
                Ask Intellexa
              </label>
              <textarea
                id="dashboard-chat-input"
                className="chat-input"
                value={inputValue}
                onChange={(event) => setInputValue(event.target.value)}
                onKeyDown={handleInputKeyDown}
                rows={2}
                placeholder="Type your question here..."
                disabled={isLoading}
              />
              <div className="chat-input-actions">
                <p className="chat-input-hint">Press Enter to send, Shift + Enter for a new line.</p>
                <button className="chat-send-button" type="submit" disabled={isLoading || !inputValue.trim()}>
                  {isLoading ? "Thinking..." : "Send"}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </section>
  );
}

export default Dashboard;
