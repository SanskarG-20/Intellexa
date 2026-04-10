import { SignOutButton, useUser } from "@clerk/clerk-react";
import { useEffect, useRef, useState } from "react";
import { useApiService } from "../services/apiService";

function createChatMessage(role, content) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content,
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
      const aiText = data?.response?.trim() || "I could not generate a response just now.";

      setMessages((prev) => [...prev, createChatMessage("assistant", aiText)]);
    } catch (error) {
      const fallback = "Unable to reach Intellexa right now. Please try again.";
      const message = error instanceof Error ? error.message : fallback;

      setErrorMessage(message || fallback);
      setMessages((prev) => [
        ...prev,
        createChatMessage(
          "assistant",
          "I hit an issue while processing that request. Please retry in a moment."
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
          {messages.map((message) => (
            <article
              key={message.id}
              className={`chat-message chat-message-${message.role}`}
            >
              <span className="chat-message-role">
                {message.role === "user" ? "You" : "Intellexa"}
              </span>
              <p>{message.content}</p>
            </article>
          ))}

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
