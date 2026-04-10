import { SignOutButton, useUser } from "@clerk/clerk-react";
import { useEffect, useRef, useState } from "react";
import { useApiService } from "../services/apiService";

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

function buildStructuredPayload(data) {
  const explanationItems = extractExplanationItems(data);
  const autopsy = extractAutopsyPayload(data);
  const ethicalCheck = isPlainObject(data?.ethical_check)
    ? data.ethical_check
    : isPlainObject(data?.audit_results)
      ? data.audit_results
      : null;
  const trustScore = data?.trust_score ?? null;
  const confidence = data?.confidence ?? null;

  return {
    autopsy,
    answer: extractMainAnswer(data),
    explanationItems,
    ethicalCheck,
    trustScore,
    confidence,
  };
}

function createChatMessage(role, content, structured = null) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
    structured,
  };
}

function Dashboard() {
  const { user } = useUser();
  const { sendMessage } = useApiService();
  const name =
    user?.firstName ||
    user?.username ||
    user?.primaryEmailAddress?.emailAddress ||
    "Builder";
  const [messages, setMessages] = useState(() => [
    createChatMessage(
      "assistant",
      "Welcome to Intellexa. Ask a question and I will respond with context-aware reasoning."
    ),
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const historyRef = useRef(null);

  useEffect(() => {
    if (!historyRef.current) return;

    historyRef.current.scrollTo({
      top: historyRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isLoading]);

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

        <div className="chat-history" ref={historyRef} aria-live="polite" aria-busy={isLoading}>
          {messages.map((message) => {
            const isAssistant = message.role === "assistant";
            const structured = message.structured;
            const hasAutopsy = Boolean(structured?.autopsy);
            const hasExplanation = Boolean(structured?.explanationItems?.length);
            const hasEthicalCheck = Boolean(
              structured?.ethicalCheck && Object.keys(structured.ethicalCheck).length
            );
            const hasTrustBlock =
              (structured?.trustScore !== null && structured?.trustScore !== undefined) ||
              (typeof structured?.confidence === "string" && structured.confidence.trim());
            const shouldRenderStructured =
              isAssistant && (hasAutopsy || hasExplanation || hasEthicalCheck || hasTrustBlock);

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

                    <section className="chat-structured-panel">
                      <h3 className="chat-panel-title">Answer</h3>
                      <p>{structured.answer || message.content}</p>
                    </section>

                    {hasExplanation ? (
                      <section className="chat-structured-panel">
                        <h3 className="chat-panel-title">Explanation</h3>
                        <ul className="chat-panel-list">
                          {structured.explanationItems.map((item, index) => (
                            <li key={`${message.id}-${index}`}>{item}</li>
                          ))}
                        </ul>
                      </section>
                    ) : null}

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
    </section>
  );
}

export default Dashboard;
