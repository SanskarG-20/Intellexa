function toPreviewText(message, limit = 72) {
  const value = String(message || "").trim();
  if (!value) {
    return "Empty message";
  }

  if (value.length <= limit) {
    return value;
  }

  return `${value.slice(0, limit).trim()}...`;
}

function toTimestampLabel(createdAt) {
  if (!createdAt) {
    return "";
  }

  const date = new Date(createdAt);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function ChatHistorySidebar({
  chats,
  activeChatId,
  isLoading,
  errorMessage,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  isNewChatDisabled,
  isInteractionDisabled,
  deletingChatId,
}) {
  return (
    <aside className="chat-sidebar" aria-label="Chat history sidebar">
      <header className="chat-sidebar-header">
        <div className="chat-sidebar-head-row">
          <div>
            <p className="chat-sidebar-kicker">History</p>
            <h2 className="chat-sidebar-title">Recent Chats</h2>
          </div>
          <button
            type="button"
            className="chat-sidebar-new-button"
            onClick={onNewChat}
            disabled={isNewChatDisabled || isInteractionDisabled}
          >
            + New Chat
          </button>
        </div>
      </header>

      <div className="chat-sidebar-list" role="list">
        {isLoading ? (
          <p className="chat-sidebar-state">Loading chat history...</p>
        ) : null}

        {!isLoading && !chats.length ? (
          <p className="chat-sidebar-state">No previous chats yet.</p>
        ) : null}

        {!isLoading
          ? chats.map((chat) => {
              const isActive = chat.id === activeChatId;
              const isDeleting = deletingChatId === chat.id;

              return (
                <div
                  key={chat.id}
                  role="listitem"
                  className={`chat-sidebar-item-shell ${isActive ? "is-active" : ""}`}
                >
                  <button
                    type="button"
                    className="chat-sidebar-item"
                    onClick={() => onSelectChat(chat.id)}
                    disabled={isInteractionDisabled || isDeleting}
                  >
                    <span className="chat-sidebar-preview">{toPreviewText(chat.message)}</span>
                    <span className="chat-sidebar-time">{toTimestampLabel(chat.created_at)}</span>
                  </button>

                  <button
                    type="button"
                    className="chat-sidebar-delete-button"
                    onClick={() => onDeleteChat(chat.id)}
                    disabled={isInteractionDisabled || isDeleting}
                    aria-label="Delete chat"
                    title="Delete chat"
                  >
                    {isDeleting ? "..." : "x"}
                  </button>
                </div>
              );
            })
          : null}
      </div>

      {errorMessage ? <p className="chat-sidebar-error">{errorMessage}</p> : null}
    </aside>
  );
}

export default ChatHistorySidebar;
