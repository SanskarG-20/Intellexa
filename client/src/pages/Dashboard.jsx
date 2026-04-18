import { SignOutButton, useUser } from "@clerk/clerk-react";
import { useCallback, useEffect, useRef, useState } from "react";
import ChatHistorySidebar from "../components/ChatHistorySidebar";
import VoiceMode from "../components/VoiceMode";
import KnowledgePanel from "../components/KnowledgePanel";
import { CodeSpaceLayout } from "../components/CodeSpace";
import { CodeWorkspaceProvider } from "../context/CodeWorkspaceContext";
import { useSpeechRecognition } from "../hooks/useSpeechRecognition";
import { useApiService } from "../services/apiService";
import {
  isSpeechSynthesisSupported,
  speakText,
  stopSpeaking,
} from "../utils/speechSynthesis";
import {
  deleteChatById,
  getChatById,
  getUserChats,
  isCloudHistoryEnabled,
  persistStructuredPayloadForChat,
  saveMessage,
  updateChatById,
} from "../services/chatHistory";

const PERSPECTIVE_TABS = [
  { key: "utilitarian", label: "Utilitarian" },
  { key: "rights_based", label: "Rights-based" },
  { key: "care_ethics", label: "Care ethics" },
];

const THINKING_STATUS_MESSAGES = [
  "Thinking...",
  "Reasoning through your request...",
  "Preparing final answer...",
];

const SEARCH_AWARE_STATUS_MESSAGES = [
  "Thinking...",
  "Searching web...",
  "Synthesizing search results...",
];

const AUTO_SCROLL_THRESHOLD_PX = 88;
const PROGRAMMATIC_SCROLL_LOCK_MS = 260;
const VOICE_AUTO_SUBMIT_ENABLED = true;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
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

function toFriendlyChatErrorMessage(rawMessage) {
  const fallback = "Unable to reach Intellexa right now. Please try again.";
  const message = String(rawMessage || "").trim();

  if (!message) {
    return fallback;
  }

  if (/401|unauthorized|token/i.test(message)) {
    return "Your session expired or token is invalid. Sign in again and retry.";
  }

  if (/network|cors|unable to reach|failed to fetch/i.test(message)) {
    return "Cannot reach the AI server. Check backend status and network, then retry.";
  }

  if (/timeout|timed out/i.test(message)) {
    return "The request timed out. Please retry with a shorter or clearer prompt.";
  }

  return message;
}

function isLikelySearchIntent(query) {
  const value = String(query || "").toLowerCase();
  if (!value) {
    return false;
  }

  return /(latest|today|current|news|breaking|live|update|202[4-9]|real[-\s]?time|stock|price|weather|election|trend)/.test(
    value
  );
}

function toSafeHttpUrl(rawUrl) {
  const value = String(rawUrl || "").trim();
  if (!value) {
    return null;
  }

  try {
    const parsed = new URL(value);
    return /^https?:$/i.test(parsed.protocol) ? parsed.toString() : null;
  } catch {
    try {
      const parsed = new URL(`https://${value}`);
      return /^https?:$/i.test(parsed.protocol) ? parsed.toString() : null;
    } catch {
      return null;
    }
  }
}

function getSourceTitleFromUrl(url) {
  if (!url) {
    return "";
  }

  try {
    return new URL(url).hostname.replace(/^www\./i, "");
  } catch {
    return "";
  }
}

function toSourceEntry(source, index) {
  const defaultLabel = `[Source ${index + 1}]`;

  if (typeof source === "string") {
    const safeUrl = toSafeHttpUrl(source);
    if (!safeUrl) {
      return null;
    }

    return {
      label: defaultLabel,
      url: safeUrl,
      title: getSourceTitleFromUrl(safeUrl),
    };
  }

  if (!isPlainObject(source)) {
    return null;
  }

  const rawUrl = source.url ?? source.link ?? source.href ?? source.source ?? source.website;
  const safeUrl = toSafeHttpUrl(rawUrl);
  if (!safeUrl) {
    return null;
  }

  const rawLabel = source.label ?? source.citation ?? source.id;
  const labelValue = String(rawLabel || "").trim();

  const rawTitle = source.title ?? source.name ?? source.domain ?? labelValue;
  const title = String(rawTitle || "").trim() || getSourceTitleFromUrl(safeUrl);

  return {
    label: defaultLabel,
    url: safeUrl,
    title,
  };
}

function extractSources(data) {
  const sourceCandidates = [
    data?.sources,
    data?.citations,
    data?.references,
    data?.web_sources,
    data?.search_results,
  ];

  let rawSources = null;

  for (const candidate of sourceCandidates) {
    if (Array.isArray(candidate) && candidate.length) {
      rawSources = candidate;
      break;
    }
  }

  if (!rawSources && isPlainObject(data?.sources)) {
    rawSources = Object.entries(data.sources).map(([label, url]) => ({ label, url }));
  }

  if (!Array.isArray(rawSources) || !rawSources.length) {
    return [];
  }

  const uniqueUrls = new Set();

  return rawSources
    .map((source, index) => toSourceEntry(source, index))
    .filter((source) => {
      if (!source) {
        return false;
      }

      if (uniqueUrls.has(source.url)) {
        return false;
      }

      uniqueUrls.add(source.url);
      return true;
    });
}

function detectSearchUsed(data, sources) {
  const explicitFlag =
    data?.search_used ??
    data?.web_search_used ??
    data?.search_performed ??
    data?.tool_search_used;

  if (typeof explicitFlag === "boolean") {
    return explicitFlag;
  }

  const toolCalls = data?.tool_calls ?? data?.tool_events ?? data?.tools;
  const toolCallText =
    typeof toolCalls === "string"
      ? toolCalls
      : Array.isArray(toolCalls) || isPlainObject(toolCalls)
        ? JSON.stringify(toolCalls)
        : "";

  if (/search_web|web_search|tool/i.test(toolCallText)) {
    return true;
  }

  return Array.isArray(sources) && sources.length > 0;
}

function renderInlineAnswer(text, sources = []) {
  const value = String(text ?? "");

  if (!value.includes("**") && !/\[source\s*\d+\]/i.test(value)) {
    return value;
  }

  const nodes = [];
  const tokenRegex = /\*\*([^*][\s\S]*?)\*\*|\[source\s*(\d+)\]/gi;
  let lastIndex = 0;
  let match;

  while ((match = tokenRegex.exec(value)) !== null) {
    const [rawMatch, boldContent, sourceIndexText] = match;
    const startIndex = match.index;

    if (startIndex > lastIndex) {
      nodes.push(value.slice(lastIndex, startIndex));
    }

    if (boldContent) {
      nodes.push(
        <strong key={`bold-${startIndex}-${rawMatch.length}`}>
          {boldContent}
        </strong>
      );
    } else if (sourceIndexText) {
      const sourceIndex = Number(sourceIndexText) - 1;
      const source = sources[sourceIndex];
      const sourceLabel = `[Source ${sourceIndexText}]`;

      if (source?.url) {
        nodes.push(
          <a
            key={`source-inline-${startIndex}`}
            href={source.url}
            target="_blank"
            rel="noreferrer noopener"
            className="chat-source-inline-link"
          >
            {sourceLabel}
          </a>
        );
      } else {
        nodes.push(sourceLabel);
      }
    }

    lastIndex = startIndex + rawMatch.length;
  }

  if (lastIndex < value.length) {
    nodes.push(value.slice(lastIndex));
  }

  return nodes.length ? nodes : value;
}

function renderFormattedAnswer(text, sources = []) {
  const value = String(text ?? "");
  if (!value.trim()) {
    return "";
  }

  const lines = value.split(/\r?\n/);
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] || "";
    const trimmed = line.trim();

    if (!trimmed) {
      blocks.push(<div key={`answer-gap-${index}`} className="chat-answer-spacer" aria-hidden="true" />);
      index += 1;
      continue;
    }

    const unorderedMatch = trimmed.match(/^[-*]\s+(.+)/);
    if (unorderedMatch) {
      const items = [];
      let listCursor = index;

      while (listCursor < lines.length) {
        const listLine = (lines[listCursor] || "").trim();
        const listMatch = listLine.match(/^[-*]\s+(.+)/);
        if (!listMatch) {
          break;
        }

        items.push(listMatch[1]);
        listCursor += 1;
      }

      blocks.push(
        <ul key={`answer-ul-${index}`} className="chat-answer-list">
          {items.map((item, itemIndex) => (
            <li key={`answer-ul-${index}-${itemIndex}`}>{renderInlineAnswer(item, sources)}</li>
          ))}
        </ul>
      );
      index = listCursor;
      continue;
    }

    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)/);
    if (orderedMatch) {
      const items = [];
      let listCursor = index;

      while (listCursor < lines.length) {
        const listLine = (lines[listCursor] || "").trim();
        const listMatch = listLine.match(/^\d+\.\s+(.+)/);
        if (!listMatch) {
          break;
        }

        items.push(listMatch[1]);
        listCursor += 1;
      }

      blocks.push(
        <ol key={`answer-ol-${index}`} className="chat-answer-ordered-list">
          {items.map((item, itemIndex) => (
            <li key={`answer-ol-${index}-${itemIndex}`}>{renderInlineAnswer(item, sources)}</li>
          ))}
        </ol>
      );
      index = listCursor;
      continue;
    }

    const isSectionHeading = /^[A-Z][A-Za-z\s]{2,32}:$/.test(trimmed);
    const isImportantLine = /^(important|key takeaway|key takeaways|note|warning|summary)\s*:/i.test(
      trimmed
    );

    blocks.push(
      <p
        key={`answer-line-${index}`}
        className={`chat-answer-line${
          isSectionHeading ? " chat-answer-line-heading" : ""
        }${isImportantLine ? " chat-answer-line-important" : ""}`}
      >
        {renderInlineAnswer(trimmed, sources)}
      </p>
    );

    index += 1;
  }

  return blocks;
}

function extractMainAnswer(data) {
  if (typeof data?.full_answer === "string" && data.full_answer.trim()) {
    return data.full_answer.trim();
  }

  if (typeof data?.final_answer === "string" && data.final_answer.trim()) {
    return data.final_answer.trim();
  }

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

function extractReframedQuery(data) {
  const value =
    data?.reframed_query ??
    data?.reframedQuery ??
    data?.neutral_reframe?.reframed_query ??
    data?.neutral_reframe?.reframedQuery;

  if (typeof value !== "string") {
    return "";
  }

  return value.trim();
}

function buildStructuredPayload(data) {
  const explanationItems = extractExplanationItems(data);
  const autopsy = extractAutopsyPayload(data);
  const perspectives = extractPerspectivePayload(data);
  const reframedQuery = extractReframedQuery(data);
  const sources = extractSources(data).map((source) => ({ ...source }));
  const searchUsed = detectSearchUsed(data, sources);
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
    reframedQuery,
    sources,
    searchUsed,
  };
}

function hasStructuredInsights(structured) {
  if (!isPlainObject(structured)) {
    return false;
  }

  const hasAutopsy = Boolean(structured.autopsy);
  const hasPerspectives = Boolean(
    structured.perspectives &&
      Object.values(structured.perspectives).some(
        (value) => typeof value === "string" && value.trim()
      )
  );
  const hasExplanation = Boolean(
    Array.isArray(structured.explanationItems) && structured.explanationItems.length
  );
  const hasTrustBlock =
    (structured.trustScore !== null && structured.trustScore !== undefined) ||
    (typeof structured.confidence === "string" && structured.confidence.trim());

  return hasAutopsy || hasPerspectives || hasExplanation || hasTrustBlock;
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

function SourcesPanel({ sources, searchUsed }) {
  const safeSources = Array.isArray(sources) ? sources.filter((source) => source?.url) : [];
  if (!safeSources.length) {
    return null;
  }

  return (
    <section className="chat-sources-panel" aria-label="Sources">
      <div className="chat-sources-header">
        <p className="chat-sources-title">Sources</p>
        {searchUsed ? <span className="chat-search-badge">Web search used</span> : null}
      </div>
      <ul className="chat-sources-list">
        {safeSources.map((source, index) => (
          <li key={`source-link-${index}`}>
            <a href={source.url} target="_blank" rel="noreferrer noopener" className="chat-source-link">
              {source.label || `[Source ${index + 1}]`}
            </a>
            <span className="chat-source-host">{source.title || source.url}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ChatInsightsPanel({ message, onClose }) {
  const structured = message?.structured;

  if (!message || !hasStructuredInsights(structured)) {
    return (
      <aside className="chat-insights-panel" aria-live="polite">
        <header className="chat-insights-header">
          <div>
            <p className="chat-insights-kicker">Response Insights</p>
            <h2 className="chat-insights-title">Analysis Panel</h2>
          </div>
        </header>
        <div className="chat-insights-empty">
          <p>Select View Analysis on any assistant response to see the full breakdown here.</p>
        </div>
      </aside>
    );
  }

  const hasAutopsy = Boolean(structured.autopsy);
  const hasPerspectives = Boolean(
    structured.perspectives &&
      Object.values(structured.perspectives).some(
        (value) => typeof value === "string" && value.trim()
      )
  );
  const hasExplanation = Boolean(structured.explanationItems?.length);
  const hasTrustBlock =
    (structured.trustScore !== null && structured.trustScore !== undefined) ||
    (typeof structured.confidence === "string" && structured.confidence.trim());

  return (
    <aside className="chat-insights-panel" aria-live="polite">
      <header className="chat-insights-header">
        <div>
          <p className="chat-insights-kicker">Response Insights</p>
          <h2 className="chat-insights-title">Analysis Panel</h2>
        </div>
        <button type="button" className="chat-insights-close" onClick={onClose}>
          Hide
        </button>
      </header>

      <div className="chat-insights-body">
        {hasAutopsy ? (
          <section className="chat-structured-panel chat-autopsy-panel">
            <h3 className="chat-panel-title chat-autopsy-title">Perspective Autopsy</h3>
            <p className="chat-autopsy-kicker">Before answer generation</p>

            <div className="chat-autopsy-group">
              <p className="chat-autopsy-label">Assumptions</p>
              {structured.autopsy.assumptions.length ? (
                <ul className="chat-panel-list">
                  {structured.autopsy.assumptions.map((item, index) => (
                    <li key={`insight-autopsy-assumption-${index}`}>{item}</li>
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
                    <li key={`insight-autopsy-angle-${index}`}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="chat-autopsy-empty">No missing angles identified.</p>
              )}
            </div>
          </section>
        ) : null}

        {hasPerspectives ? <PerspectiveTabs perspectives={structured.perspectives} /> : null}

        {hasExplanation ? <ExplanationPanel items={structured.explanationItems} /> : null}

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
    </aside>
  );
}

function createChatMessage(role, content, structured = null, options = {}) {
  return {
    id: `${role}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    role,
    content: String(content ?? ""),
    structured,
    animate: Boolean(options.animate),
    isError: Boolean(options.isError),
  };
}

const WELCOME_MESSAGE =
  "Welcome to Intellexa. Ask a question and I will respond with context-aware reasoning.";

function buildMessagesFromSavedChat(chat) {
  const items = [];
  const question = String(chat?.message || "").trim();
  const answer = String(chat?.response || "").trim();
  const structuredPayload = isPlainObject(chat?.structured_payload)
    ? chat.structured_payload
    : null;
  let assistantMessageId = null;

  if (question) {
    items.push(createChatMessage("user", question));
  }

  if (answer) {
    const assistantMessage = createChatMessage("assistant", answer, structuredPayload);
    items.push(assistantMessage);

    if (hasStructuredInsights(assistantMessage.structured)) {
      assistantMessageId = assistantMessage.id;
    }
  }

  if (!items.length) {
    items.push(createChatMessage("assistant", "This chat item has no saved content."));
  }

  return {
    items,
    assistantMessageId,
  };
}

function Dashboard() {
  const { user } = useUser();
  const { sendMessage } = useApiService();
  const {
    isSupported: isSpeechRecognitionSupported,
    isListening,
    transcript,
    interimTranscript,
    error: speechRecognitionError,
    startListening,
    stopListening,
    resetTranscript,
    clearError: clearSpeechRecognitionError,
  } = useSpeechRecognition();
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
  const [isSearchLikely, setIsSearchLikely] = useState(false);
  const [activeInsightMessageId, setActiveInsightMessageId] = useState(null);
  const [insightLoadingMessageId, setInsightLoadingMessageId] = useState(null);
  const [deletingChatId, setDeletingChatId] = useState(null);
  const [errorMessage, setErrorMessage] = useState("");
  const [voiceStatusMessage, setVoiceStatusMessage] = useState("");
  const [isVoiceOutputEnabled, setIsVoiceOutputEnabled] = useState(true);
  const [isVoiceModeActive, setIsVoiceModeActive] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [voiceRate, setVoiceRate] = useState(1);
  const [thinkingStepIndex, setThinkingStepIndex] = useState(0);
  const [typingState, setTypingState] = useState({
    messageId: null,
    visibleText: "",
    visibleLength: 0,
  });
  const [activeView, setActiveView] = useState("chat"); // "chat" or "knowledge"
  const historyRef = useRef(null);
  const messagesEndRef = useRef(null);
  const typingRafRef = useRef(null);
  const typedMessageIdsRef = useRef(new Set());
  const shouldAutoScrollRef = useRef(true);
  const autoScrollRafRef = useRef(null);
  const programmaticScrollLockUntilRef = useRef(0);
  const requestAbortControllerRef = useRef(null);
  const userInterruptedRef = useRef(false);
  const shouldAutoSubmitVoiceRef = useRef(false);

  const activeInsightMessage = activeInsightMessageId
    ? messages.find(
        (message) =>
          message.id === activeInsightMessageId && hasStructuredInsights(message.structured)
      ) || null
    : null;
  const loadingStatusMessages = isSearchLikely
    ? SEARCH_AWARE_STATUS_MESSAGES
    : THINKING_STATUS_MESSAGES;
  const isResponseInterruptible = isLoading || Boolean(typingState.messageId);
  const isSpeechSynthesisAvailable = isSpeechSynthesisSupported();
  const liveTranscript = [transcript, interimTranscript].filter(Boolean).join(" ").trim();
  const cloudHistoryEnabled = isCloudHistoryEnabled();

  const stopVoicePlayback = useCallback(() => {
    stopSpeaking();
    setIsSpeaking(false);
  }, []);

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

  const stopTypingAnimation = useCallback(() => {
    if (typingRafRef.current !== null) {
      window.cancelAnimationFrame(typingRafRef.current);
      typingRafRef.current = null;
    }

    setTypingState((current) => {
      if (!current.messageId) {
        return current;
      }

      return {
        messageId: null,
        visibleText: "",
        visibleLength: 0,
      };
    });
  }, []);

  const handleHistoryScroll = useCallback(() => {
    const historyNode = historyRef.current;
    if (!historyNode) {
      return;
    }

    if (window.performance.now() < programmaticScrollLockUntilRef.current) {
      return;
    }

    const distanceFromBottom =
      historyNode.scrollHeight - historyNode.scrollTop - historyNode.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX;
  }, []);

  const scrollHistoryToBottom = useCallback((behavior = "auto") => {
    const historyNode = historyRef.current;
    if (!historyNode) {
      return;
    }

    programmaticScrollLockUntilRef.current =
      window.performance.now() + (behavior === "smooth" ? PROGRAMMATIC_SCROLL_LOCK_MS + 220 : PROGRAMMATIC_SCROLL_LOCK_MS);

    historyNode.scrollTo({
      top: historyNode.scrollHeight,
      behavior,
    });
  }, []);

  const queueAutoScroll = useCallback(
    (behavior = "auto") => {
      if (!shouldAutoScrollRef.current) {
        return;
      }

      if (autoScrollRafRef.current !== null) {
        window.cancelAnimationFrame(autoScrollRafRef.current);
      }

      autoScrollRafRef.current = window.requestAnimationFrame(() => {
        autoScrollRafRef.current = null;
        scrollHistoryToBottom(behavior);
      });
    },
    [scrollHistoryToBottom]
  );

  const startTypingAnimation = useCallback(
    (messageId, fullText) => {
      const text = String(fullText || "");

      stopTypingAnimation();

      if (!text) {
        return;
      }

      const totalLength = text.length;
      const step = totalLength > 420 ? 4 : totalLength > 220 ? 2 : 1;
      const durationMs = Math.max(420, Math.min(2600, totalLength * 16));
      let startTime = null;
      let previousLength = 0;

      setTypingState({
        messageId,
        visibleText: "",
        visibleLength: 0,
      });

      const tick = (timestamp) => {
        if (startTime === null) {
          startTime = timestamp;
        }

        const progress = Math.min(1, (timestamp - startTime) / durationMs);
        const scaledLength = Math.floor(totalLength * progress);
        const steppedLength =
          progress < 1
            ? Math.floor(scaledLength / step) * step
            : totalLength;
        const nextLength = Math.max(previousLength, Math.min(totalLength, steppedLength));

        if (nextLength !== previousLength || progress === 1) {
          previousLength = nextLength;
          setTypingState({
            messageId,
            visibleText: text.slice(0, nextLength),
            visibleLength: nextLength,
          });
        }

        if (progress < 1) {
          typingRafRef.current = window.requestAnimationFrame(tick);
          return;
        }

        typingRafRef.current = null;
        setTypingState({
          messageId: null,
          visibleText: "",
          visibleLength: 0,
        });
      };

      typingRafRef.current = window.requestAnimationFrame(tick);
    },
    [stopTypingAnimation]
  );

  const interruptTypingResponse = useCallback(() => {
    if (!typingState.messageId) {
      return false;
    }

    const partialText = String(typingState.visibleText || "").trimEnd();

    setMessages((prev) =>
      prev.map((message) =>
        message.id === typingState.messageId
          ? {
              ...message,
              content: partialText || "Generation stopped.",
              animate: false,
            }
          : message
      )
    );

    stopTypingAnimation();
    return true;
  }, [stopTypingAnimation, typingState.messageId, typingState.visibleText]);

  const submitMessage = useCallback(
    async (rawMessage, options = {}) => {
      const nextMessage = String(rawMessage || "").trim();
      const shouldSpeakResponse = options?.shouldSpeakResponse ?? isVoiceOutputEnabled;
      const appendInterruptMessage = options?.appendInterruptMessage ?? true;
      const animateResponse = options?.animateResponse ?? true;
      const clearInput = options?.clearInput ?? true;
      const voiceMode = Boolean(options?.voiceMode);
      const suppressErrorBanner = Boolean(options?.suppressErrorBanner);
      const suppressAssistantErrorMessage = Boolean(options?.suppressAssistantErrorMessage);

      if (!nextMessage || isResponseInterruptible) {
        return {
          ok: false,
          interrupted: false,
          error: "Cannot submit an empty message or while another response is active.",
        };
      }

      userInterruptedRef.current = false;
      const requestAbortController = new AbortController();
      requestAbortControllerRef.current = requestAbortController;

      stopTypingAnimation();
      stopVoicePlayback();
      shouldAutoScrollRef.current = true;
      setThinkingStepIndex(0);
      setIsSearchLikely(isLikelySearchIntent(nextMessage));
      setErrorMessage("");
      setVoiceStatusMessage("");
      setActiveInsightMessageId(null);
      if (clearInput) {
        setInputValue("");
      }
      setMessages((prev) => [...prev, createChatMessage("user", nextMessage)]);
      setIsLoading(true);

      try {
        const data = await sendMessage(nextMessage, {
          signal: requestAbortController.signal,
          voiceMode,
        });

        if (userInterruptedRef.current) {
          return {
            ok: false,
            interrupted: true,
            error: "Request canceled by user.",
          };
        }

        const structuredPayload = buildStructuredPayload(data);
        const isolatedStructuredPayload = {
          ...structuredPayload,
          sources: Array.isArray(structuredPayload.sources)
            ? structuredPayload.sources.map((source) => ({ ...source }))
            : [],
        };
        const aiText = isolatedStructuredPayload.answer || "I could not generate a response just now.";
        const assistantMessage = createChatMessage("assistant", aiText, isolatedStructuredPayload, {
          animate: animateResponse,
        });

        setMessages((prev) => [...prev, assistantMessage]);

        if (hasStructuredInsights(assistantMessage.structured)) {
          setActiveInsightMessageId(assistantMessage.id);
        }

        if (shouldSpeakResponse && aiText && isSpeechSynthesisAvailable) {
          const speechResult = speakText(aiText, {
            rate: voiceRate,
            onStart: () => {
              setIsSpeaking(true);
            },
            onEnd: () => {
              setIsSpeaking(false);
            },
            onError: () => {
              setIsSpeaking(false);
            },
          });

          if (!speechResult.ok && speechResult.error) {
            setVoiceStatusMessage(speechResult.error);
          }
        }

        if (userId) {
          try {
            let preferredChatId = activeChatId;

            if (activeChatId) {
              await updateChatById(activeChatId, userId, nextMessage, aiText, isolatedStructuredPayload);
            } else {
              const saved = await saveMessage(userId, nextMessage, aiText, isolatedStructuredPayload);
              preferredChatId = saved?.id || null;
            }

            await loadHistory(preferredChatId);
          } catch (historyError) {
            const message =
              historyError instanceof Error
                ? historyError.message
                : "Failed to save chat history.";
            setHistoryErrorMessage(message);
          }
        }

        return {
          ok: true,
          interrupted: false,
          answer: aiText,
          fullAnswer: aiText,
          shortAnswer:
            typeof data?.short_answer === "string" && data.short_answer.trim()
              ? data.short_answer.trim()
              : "",
          structuredPayload: isolatedStructuredPayload,
          searchUsed: Boolean(isolatedStructuredPayload?.searchUsed),
          sources: Array.isArray(isolatedStructuredPayload?.sources)
            ? isolatedStructuredPayload.sources
            : [],
          explanationItems: Array.isArray(isolatedStructuredPayload?.explanationItems)
            ? isolatedStructuredPayload.explanationItems
            : [],
        };
      } catch (error) {
        const rawMessage = error instanceof Error ? error.message : "";
        const isInterrupted =
          userInterruptedRef.current ||
          /request canceled|cancelled|canceled|aborted|abort/i.test(rawMessage);

        if (isInterrupted) {
          setErrorMessage("");
          if (appendInterruptMessage) {
            setMessages((prev) => [...prev, createChatMessage("assistant", "Generation stopped.")]);
          }
          return {
            ok: false,
            interrupted: true,
            error: "Request canceled by user.",
          };
        }

        const userVisibleMessage = toFriendlyChatErrorMessage(rawMessage);

        if (suppressErrorBanner) {
          setErrorMessage("");
        } else {
          setErrorMessage(userVisibleMessage);
        }

        if (!suppressAssistantErrorMessage) {
          setMessages((prev) => [
            ...prev,
            createChatMessage(
              "assistant",
              `I hit an issue while processing that request: ${userVisibleMessage}`,
              null,
              { isError: true }
            ),
          ]);
        }

        return {
          ok: false,
          interrupted: false,
          error: userVisibleMessage,
        };
      } finally {
        requestAbortControllerRef.current = null;
        setIsLoading(false);
        setIsSearchLikely(false);
      }
    },
    [
      activeChatId,
      isResponseInterruptible,
      isSpeechSynthesisAvailable,
      isVoiceOutputEnabled,
      loadHistory,
      sendMessage,
      stopTypingAnimation,
      stopVoicePlayback,
      userId,
      voiceRate,
    ]
  );

  const handleInterruptResponse = useCallback(() => {
    userInterruptedRef.current = true;
    const didInterruptTyping = interruptTypingResponse();

    if (requestAbortControllerRef.current) {
      requestAbortControllerRef.current.abort();
      requestAbortControllerRef.current = null;
    }

    if (isLoading) {
      setIsLoading(false);
      setIsSearchLikely(false);
    }

    stopVoicePlayback();

    if (didInterruptTyping) {
      setErrorMessage("");
    }
  }, [interruptTypingResponse, isLoading, stopVoicePlayback]);

  const handleMicToggle = useCallback(() => {
    if (!isSpeechRecognitionSupported) {
      setVoiceStatusMessage("Voice not supported in this browser.");
      return;
    }

    if (isListening) {
      shouldAutoSubmitVoiceRef.current = false;
      stopListening();
      return;
    }

    if (isResponseInterruptible) {
      return;
    }

    setVoiceStatusMessage("");
    clearSpeechRecognitionError();
    resetTranscript();
    stopVoicePlayback();
    shouldAutoSubmitVoiceRef.current = VOICE_AUTO_SUBMIT_ENABLED;
    const started = startListening();

    if (!started) {
      shouldAutoSubmitVoiceRef.current = false;
      setVoiceStatusMessage("Could not start microphone listening.");
    }
  }, [
    clearSpeechRecognitionError,
    isListening,
    isResponseInterruptible,
    isSpeechRecognitionSupported,
    resetTranscript,
    startListening,
    stopListening,
    stopVoicePlayback,
  ]);

  const handleVoiceOutputToggle = useCallback(() => {
    if (!isSpeechSynthesisAvailable) {
      setVoiceStatusMessage("Voice output is not supported in this browser.");
      return;
    }

    setIsVoiceOutputEnabled((current) => {
      const next = !current;
      if (!next) {
        stopVoicePlayback();
      }
      return next;
    });
  }, [isSpeechSynthesisAvailable, stopVoicePlayback]);

  const handleStopSpeaking = useCallback(() => {
    stopVoicePlayback();
  }, [stopVoicePlayback]);

  const handleStartVoiceMode = useCallback(() => {
    userInterruptedRef.current = true;
    stopTypingAnimation();

    if (requestAbortControllerRef.current) {
      requestAbortControllerRef.current.abort();
      requestAbortControllerRef.current = null;
    }

    if (isLoading) {
      setIsLoading(false);
      setIsSearchLikely(false);
    }

    stopListening();
    stopVoicePlayback();
    resetTranscript();
    shouldAutoSubmitVoiceRef.current = false;
    setIsVoiceModeActive(true);
    setVoiceStatusMessage("");
    setErrorMessage("");
  }, [isLoading, resetTranscript, stopListening, stopTypingAnimation, stopVoicePlayback]);

  const handleStopVoiceMode = useCallback(() => {
    stopListening();
    stopVoicePlayback();
    resetTranscript();
    shouldAutoSubmitVoiceRef.current = false;
    setIsVoiceModeActive(false);
    setVoiceStatusMessage("");
  }, [resetTranscript, stopListening, stopVoicePlayback]);

  const handleVoiceModeSubmit = useCallback(
    async (spokenText) => {
      return submitMessage(spokenText, {
        shouldSpeakResponse: false,
        appendInterruptMessage: false,
        animateResponse: false,
        clearInput: false,
        voiceMode: true,
        suppressErrorBanner: true,
        suppressAssistantErrorMessage: true,
      });
    },
    [submitMessage]
  );

  useEffect(() => {
    if (!shouldAutoScrollRef.current) {
      return undefined;
    }

    const behavior = isLoading || Boolean(typingState.messageId) ? "auto" : "smooth";
    queueAutoScroll(behavior);
    return undefined;
  }, [messages.length, typingState.visibleLength, isLoading, typingState.messageId, queueAutoScroll]);

  useEffect(() => {
    const historyNode = historyRef.current;
    if (!historyNode) {
      return undefined;
    }

    const mutationObserver = new MutationObserver(() => {
      queueAutoScroll("auto");
    });

    mutationObserver.observe(historyNode, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    let resizeObserver = null;
    if (typeof window.ResizeObserver !== "undefined") {
      resizeObserver = new window.ResizeObserver(() => {
        queueAutoScroll("auto");
      });
      resizeObserver.observe(historyNode);
    }

    const handleViewportResize = () => {
      queueAutoScroll("auto");
    };

    window.addEventListener("resize", handleViewportResize);

    return () => {
      mutationObserver.disconnect();
      if (resizeObserver) {
        resizeObserver.disconnect();
      }
      window.removeEventListener("resize", handleViewportResize);
    };
  }, [queueAutoScroll]);

  useEffect(() => {
    if (isLoading) {
      return;
    }

    if (typingState.messageId) {
      return;
    }

    const nextMessageToAnimate = [...messages]
      .reverse()
      .find(
        (message) =>
          message.role === "assistant" &&
          message.animate &&
          !typedMessageIdsRef.current.has(message.id)
      );

    if (!nextMessageToAnimate) {
      return;
    }

    typedMessageIdsRef.current.add(nextMessageToAnimate.id);
    startTypingAnimation(nextMessageToAnimate.id, nextMessageToAnimate.content);
  }, [isLoading, messages, startTypingAnimation, typingState.messageId]);

  useEffect(() => {
    if (!isLoading) {
      setThinkingStepIndex(0);
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setThinkingStepIndex((current) => (current + 1) % loadingStatusMessages.length);
    }, 1350);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isLoading, loadingStatusMessages.length]);

  useEffect(() => {
    if (!liveTranscript) {
      return;
    }

    setInputValue(liveTranscript);
  }, [liveTranscript]);

  useEffect(() => {
    if (!speechRecognitionError) {
      return;
    }

    setVoiceStatusMessage(speechRecognitionError);
  }, [speechRecognitionError]);

  useEffect(() => {
    if (isListening) {
      return;
    }

    if (!shouldAutoSubmitVoiceRef.current) {
      return;
    }

    shouldAutoSubmitVoiceRef.current = false;
    const finalTranscript = String(transcript || "").trim();

    if (!finalTranscript) {
      return;
    }

    if (isResponseInterruptible) {
      setVoiceStatusMessage("Voice captured. Send once current response is complete.");
      return;
    }

    void submitMessage(finalTranscript);
    resetTranscript();
  }, [isListening, isResponseInterruptible, resetTranscript, submitMessage, transcript]);

  useEffect(() => {
    if (isVoiceOutputEnabled) {
      return;
    }

    stopVoicePlayback();
  }, [isVoiceOutputEnabled, stopVoicePlayback]);

  useEffect(() => {
    return () => {
      if (typingRafRef.current !== null) {
        window.cancelAnimationFrame(typingRafRef.current);
      }

      if (autoScrollRafRef.current !== null) {
        window.cancelAnimationFrame(autoScrollRafRef.current);
      }

      if (requestAbortControllerRef.current) {
        requestAbortControllerRef.current.abort();
        requestAbortControllerRef.current = null;
      }

      stopListening();
      stopVoicePlayback();
    };
  }, [stopListening, stopVoicePlayback]);

  useEffect(() => {
    if (!activeInsightMessageId) {
      return;
    }

    const stillExists = messages.some((message) => message.id === activeInsightMessageId);
    if (!stillExists) {
      setActiveInsightMessageId(null);
    }
  }, [activeInsightMessageId, messages]);

  const handleSelectHistoryItem = useCallback(async (chatId) => {
    if (!chatId || isLoading || insightLoadingMessageId) {
      return;
    }

    stopTypingAnimation();
    setHistoryErrorMessage("");
    setErrorMessage("");
    setInputValue("");
    setIsSearchLikely(false);
    setActiveChatId(chatId);
    setActiveInsightMessageId(null);
    shouldAutoScrollRef.current = true;

    try {
      const chat = await getChatById(chatId);

      if (!chat) {
        setMessages([createChatMessage("assistant", "Could not load this conversation.")]);
        return;
      }

      const savedChatMessages = buildMessagesFromSavedChat(chat);
      setMessages(savedChatMessages.items);
      setActiveInsightMessageId(savedChatMessages.assistantMessageId);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to load selected chat history.";
      setHistoryErrorMessage(message);
    }
  }, [insightLoadingMessageId, isLoading, stopTypingAnimation]);

  const handleStartNewChat = useCallback(() => {
    stopTypingAnimation();
    shouldAutoScrollRef.current = true;
    typedMessageIdsRef.current = new Set();

    setActiveChatId(null);
    setActiveInsightMessageId(null);
    setInsightLoadingMessageId(null);
    setIsSearchLikely(false);
    setErrorMessage("");
    setHistoryErrorMessage("");
    setInputValue("");
    setMessages([createChatMessage("assistant", WELCOME_MESSAGE)]);
  }, [stopTypingAnimation]);

  const handleDeleteChat = useCallback(
    async (chatId) => {
      const safeChatId = String(chatId || "").trim();
      if (!safeChatId || !userId || isLoading || insightLoadingMessageId || deletingChatId) {
        return;
      }

      const targetChat = chatHistoryItems.find((chat) => chat.id === safeChatId);
      const previewText = targetChat?.message ? `\"${String(targetChat.message).slice(0, 48)}\"` : "this chat";
      const shouldDelete = window.confirm(`Delete ${previewText}? This cannot be undone.`);
      if (!shouldDelete) {
        return;
      }

      setDeletingChatId(safeChatId);
      setHistoryErrorMessage("");

      try {
        await deleteChatById(safeChatId, userId);
        setChatHistoryItems((prev) => prev.filter((chat) => chat.id !== safeChatId));

        if (activeChatId === safeChatId) {
          handleStartNewChat();
        }
      } catch (error) {
        const message =
          error instanceof Error
            ? error.message
            : "Failed to delete chat.";
        setHistoryErrorMessage(message);
      } finally {
        setDeletingChatId(null);
      }
    },
    [
      activeChatId,
      chatHistoryItems,
      deletingChatId,
      handleStartNewChat,
      insightLoadingMessageId,
      isLoading,
      userId,
    ]
  );

  const handleViewInsightsForMessage = useCallback(
    async (messageId, prompt, hasInsights) => {
      if (!messageId || isLoading || insightLoadingMessageId) {
        return;
      }

      if (hasInsights) {
        setActiveInsightMessageId((current) => (current === messageId ? null : messageId));
        return;
      }

      const safePrompt = String(prompt || "").trim();
      if (!safePrompt) {
        setErrorMessage("Cannot generate insights for this response because the original query is missing.");
        return;
      }

      setInsightLoadingMessageId(messageId);
      setErrorMessage("");

      try {
        const data = await sendMessage(safePrompt);
        const structuredPayload = buildStructuredPayload(data);

        if (!hasStructuredInsights(structuredPayload)) {
          throw new Error("No structured analysis was returned for this response.");
        }

        setMessages((prev) =>
          prev.map((message) =>
            message.id === messageId
              ? {
                  ...message,
                  structured: structuredPayload,
                }
              : message
          )
        );
        setActiveInsightMessageId(messageId);

        if (activeChatId) {
          try {
            await persistStructuredPayloadForChat(activeChatId, structuredPayload);
            setChatHistoryItems((prev) =>
              prev.map((item) =>
                item.id === activeChatId
                  ? {
                      ...item,
                      structured_payload: structuredPayload,
                    }
                  : item
              )
            );
          } catch {
            // Ignore persistence fallback errors; in-memory insights remain available.
          }
        }
      } catch (error) {
        const rawMessage = error instanceof Error ? error.message : "";
        setErrorMessage(toFriendlyChatErrorMessage(rawMessage));
      } finally {
        setInsightLoadingMessageId(null);
      }
    },
    [activeChatId, insightLoadingMessageId, isLoading, sendMessage]
  );

  useEffect(() => {
    stopTypingAnimation();
    stopVoicePlayback();
    stopListening();
    resetTranscript();
    shouldAutoSubmitVoiceRef.current = false;
    setIsVoiceModeActive(false);
    shouldAutoScrollRef.current = true;
    typedMessageIdsRef.current = new Set();
    setActiveInsightMessageId(null);
    setInsightLoadingMessageId(null);
    setIsSearchLikely(false);
    setErrorMessage("");
    setVoiceStatusMessage("");
    setHistoryErrorMessage("");
    setInputValue("");
    setMessages([createChatMessage("assistant", WELCOME_MESSAGE)]);
  }, [resetTranscript, stopListening, stopTypingAnimation, stopVoicePlayback, userId]);

  const handleSubmit = (event) => {
    event.preventDefault();
    void submitMessage(inputValue);
  };

  const handleInputKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!isResponseInterruptible) {
        void submitMessage(inputValue);
      }
    }
  };

  return (
    <section className="dashboard-page">
      <div className="dashboard-bg-text" aria-hidden="true">
        <p className="dashboard-bg-line">
          INTELLEXA // TRUST-FIRST ANALYSIS // CONTEXT MEMORY // MULTI-STEP REASONING // VERIFIED SOURCES
        </p>
        <p className="dashboard-bg-line">
          PERSPECTIVE ENGINE // TRANSPARENT OUTPUT // AGENTIC SEARCH // CONFIDENCE METRICS // USER CONTEXT
        </p>
        <p className="dashboard-bg-line">
          ETHICAL GUARDRAILS // TRACEABLE ANSWERS // REAL-TIME INSIGHTS // ACCOUNTABLE AI WORKSPACE
        </p>
        <p className="dashboard-bg-line">
          DECISION INTELLIGENCE // SEARCH CITATIONS // LONG-FORM REASONING // SAFE RESPONSE LAYERS
        </p>
        <p className="dashboard-bg-line">
          MEMORY-AWARE ASSISTANT // EXPLAINABILITY MODE // SOURCE-DRIVEN OUTPUT // TRUST SIGNALS
        </p>
        <p className="dashboard-bg-line">
          HUMAN-CENTERED AI // CLARITY BY DESIGN // FAST ITERATION LOOP // VERIFIABLE INSIGHT ENGINE
        </p>
      </div>

      <div className="dashboard-card dashboard-chat-card">
        <header className="dashboard-header">
          <div>
            <p className="dashboard-kicker">INTELLEXA DASHBOARD</p>
            <h1 className="dashboard-title">Welcome, {name}</h1>
            <p className="dashboard-subtitle">Your authenticated AI chat workspace.</p>
          </div>
          <div className="dashboard-header-actions">
            <div className="dashboard-view-tabs">
              <button
                type="button"
                className={`dashboard-view-tab ${activeView === "chat" ? "is-active" : ""}`}
                onClick={() => setActiveView("chat")}
              >
                Chat
              </button>
              <button
                type="button"
                className={`dashboard-view-tab ${activeView === "code" ? "is-active" : ""}`}
                onClick={() => setActiveView("code")}
              >
                Code
              </button>
              <button
                type="button"
                className={`dashboard-view-tab ${activeView === "knowledge" ? "is-active" : ""}`}
                onClick={() => setActiveView("knowledge")}
              >
                Knowledge
              </button>
            </div>
            <button
              type="button"
              className={`dashboard-voice-mode-toggle ${isVoiceModeActive ? "is-active" : ""}`}
              onClick={isVoiceModeActive ? handleStopVoiceMode : handleStartVoiceMode}
            >
              {isVoiceModeActive ? "Stop Voice Mode" : "Start Voice Mode"}
            </button>

            <SignOutButton>
              <button className="dashboard-signout" type="button">
                Sign out
              </button>
            </SignOutButton>
          </div>
        </header>

        {errorMessage ? (
          <p className="chat-error-banner" role="status">
            {errorMessage}
          </p>
        ) : null}

        {isVoiceModeActive ? (
          <VoiceMode
            onSubmitVoiceQuery={handleVoiceModeSubmit}
            onStopVoiceMode={handleStopVoiceMode}
            onInterruptActiveResponse={handleInterruptResponse}
          />
        ) : activeView === "code" ? (
          <CodeWorkspaceProvider>
            <CodeSpaceLayout />
          </CodeWorkspaceProvider>
        ) : activeView === "knowledge" ? (
          <KnowledgePanel />
        ) : (
        <div className="dashboard-chat-layout">
          <ChatHistorySidebar
            chats={chatHistoryItems}
            activeChatId={activeChatId}
            isLoading={isHistoryLoading}
            errorMessage={historyErrorMessage}
            isCloudHistoryEnabled={cloudHistoryEnabled}
            onSelectChat={handleSelectHistoryItem}
            onNewChat={handleStartNewChat}
            onDeleteChat={handleDeleteChat}
            isNewChatDisabled={isLoading || Boolean(deletingChatId)}
            isInteractionDisabled={Boolean(isLoading || insightLoadingMessageId || deletingChatId)}
            deletingChatId={deletingChatId}
          />

          <div className="dashboard-chat-main">
            <div className="dashboard-chat-content">
              <div className="dashboard-chat-thread">
                <div
                  className="chat-history"
                  ref={historyRef}
                  onScroll={handleHistoryScroll}
                  aria-live="polite"
                  aria-busy={isLoading}
                >
                  {messages.map((message, index) => {
                    const isAssistant = message.role === "assistant";
                    const isTypingMessage = isAssistant && typingState.messageId === message.id;
                    const displayedContent = isTypingMessage ? typingState.visibleText : message.content;
                    const responseText = displayedContent || (isTypingMessage ? "" : message.content);
                    const reframedQuery = String(
                      message.structured?.reframedQuery ||
                        message.structured?.reframed_query ||
                        message.structured?.neutral_reframe?.reframed_query ||
                        message.structured?.neutral_reframe?.reframedQuery ||
                        ""
                    ).trim();
                    const hasReframedQuery = isAssistant && Boolean(reframedQuery);
                    const messageSources = Array.isArray(message.structured?.sources)
                      ? message.structured.sources
                      : [];
                    const hasSources = isAssistant && messageSources.length > 0;
                    const searchUsed = Boolean(message.structured?.searchUsed);
                    const previousMessage = index > 0 ? messages[index - 1] : null;
                    const insightPrompt =
                      previousMessage?.role === "user" ? previousMessage.content : "";
                    const hasInsights = isAssistant && hasStructuredInsights(message.structured);
                    const canRequestInsights =
                      isAssistant &&
                      !message.isError &&
                      !isTypingMessage &&
                      Boolean(String(insightPrompt || "").trim());
                    const shouldShowInsightAction = hasInsights || canRequestInsights;
                    const isInsightActive = hasInsights && activeInsightMessageId === message.id;
                    const isInsightLoading = insightLoadingMessageId === message.id;

                    return (
                      <article
                        key={message.id}
                        className={`chat-message chat-message-${message.role}${
                          message.isError ? " chat-message-error" : ""
                        }`}
                      >
                        <span className="chat-message-role">
                          {message.role === "user" ? "You" : "Intellexa"}
                        </span>

                        {hasReframedQuery ? (
                          <p className="chat-reframed-query" aria-label="Reframed Question">
                            <span className="chat-reframed-query-label">
                              <span className="chat-reframed-query-icon" aria-hidden="true">
                                <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
                                  <path
                                    d="M4 5a3 3 0 0 1 3-3h7.586a3 3 0 0 1 2.121.879l2.414 2.414A3 3 0 0 1 20 7.414V19a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3V5Zm12 1h2.586l-2.586-2.586V6ZM8 11a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2H8Zm0 4a1 1 0 1 0 0 2h5a1 1 0 1 0 0-2H8Z"
                                    fill="currentColor"
                                  />
                                </svg>
                              </span>
                              Reframed Question:
                            </span>{" "}
                            <span className="chat-reframed-query-text">&quot;{reframedQuery}&quot;</span>
                          </p>
                        ) : null}

                        <div className="chat-response-text">
                          {renderFormattedAnswer(responseText, messageSources)}
                          {isTypingMessage ? (
                            <span className="chat-typing-cursor" aria-hidden="true">
                              |
                            </span>
                          ) : null}
                        </div>

                        {hasSources ? (
                          <SourcesPanel sources={messageSources} searchUsed={searchUsed} />
                        ) : null}

                        {shouldShowInsightAction ? (
                          <div className="chat-message-actions">
                            <button
                              type="button"
                              className={`chat-insight-trigger ${isInsightActive ? "is-active" : ""}`}
                              onClick={() =>
                                void handleViewInsightsForMessage(
                                  message.id,
                                  insightPrompt,
                                  hasInsights
                                )
                              }
                              disabled={isInsightLoading || isLoading}
                            >
                              {isInsightLoading
                                ? "Generating..."
                                : isInsightActive
                                  ? "Hide Analysis"
                                  : "View Analysis"}
                            </button>
                          </div>
                        ) : null}
                      </article>
                    );
                  })}

                  {isLoading ? (
                    <article
                      className="chat-message chat-message-assistant chat-message-loading"
                      aria-label="Intellexa is thinking"
                      role="status"
                    >
                      <span className="chat-message-role">Intellexa</span>
                      <p className="chat-thinking-label">
                        {loadingStatusMessages[thinkingStepIndex % loadingStatusMessages.length]}
                      </p>
                      <div className="chat-typing-dots" aria-hidden="true">
                        <span />
                        <span />
                        <span />
                      </div>
                      <div className="chat-thinking-progress" aria-hidden="true">
                        <span />
                      </div>
                    </article>
                  ) : null}

                  <div ref={messagesEndRef} className="chat-scroll-anchor" aria-hidden="true" />
                </div>

                <form className="chat-input-form" onSubmit={handleSubmit}>
                  <label className="chat-input-label" htmlFor="dashboard-chat-input">
                    Ask Intellexa
                  </label>
                  <textarea
                    id="dashboard-chat-input"
                    className="chat-input"
                    value={inputValue}
                    onChange={(event) => {
                      if (errorMessage) {
                        setErrorMessage("");
                      }

                      setInputValue(event.target.value);
                    }}
                    onKeyDown={handleInputKeyDown}
                    rows={2}
                    placeholder="Type your question here..."
                    disabled={isLoading}
                  />
                  <div className="chat-input-actions">
                    <div className="chat-input-meta">
                      <p className="chat-input-hint">Press Enter to send, Shift + Enter for a new line.</p>

                      <div className="chat-voice-controls">
                        <button
                          type="button"
                          className={`chat-voice-button chat-mic-button${isListening ? " is-listening" : ""}`}
                          onClick={handleMicToggle}
                          disabled={isResponseInterruptible && !isListening}
                          aria-pressed={isListening}
                          title={isListening ? "Stop listening" : "Start voice input"}
                        >
                          {isListening ? "Listening..." : "Mic"}
                        </button>

                        <button
                          type="button"
                          className={`chat-voice-button${isVoiceOutputEnabled ? " is-active" : ""}`}
                          onClick={handleVoiceOutputToggle}
                          aria-pressed={isVoiceOutputEnabled}
                          title="Toggle voice output"
                        >
                          {isVoiceOutputEnabled ? "Voice On" : "Voice Off"}
                        </button>

                        <label className="chat-voice-rate-wrap" htmlFor="chat-voice-rate-select">
                          <span>Speed</span>
                          <select
                            id="chat-voice-rate-select"
                            className="chat-voice-rate-select"
                            value={String(voiceRate)}
                            onChange={(event) => setVoiceRate(Number(event.target.value))}
                            disabled={!isVoiceOutputEnabled}
                          >
                            <option value="0.9">0.9x</option>
                            <option value="1">1.0x</option>
                            <option value="1.15">1.15x</option>
                          </select>
                        </label>

                        {isSpeaking ? (
                          <button
                            type="button"
                            className="chat-voice-button chat-voice-stop-button"
                            onClick={handleStopSpeaking}
                            title="Stop speaking"
                          >
                            Stop Voice
                          </button>
                        ) : null}
                      </div>

                      {voiceStatusMessage ? (
                        <p className="chat-voice-status chat-voice-status-error">{voiceStatusMessage}</p>
                      ) : isListening ? (
                        <p className="chat-voice-status">Listening for your query...</p>
                      ) : isSpeaking ? (
                        <p className="chat-voice-status">Speaking response...</p>
                      ) : null}
                    </div>

                    <button
                      className={`chat-send-button${isResponseInterruptible ? " chat-stop-button" : ""}`}
                      type={isResponseInterruptible ? "button" : "submit"}
                      onClick={isResponseInterruptible ? handleInterruptResponse : undefined}
                      disabled={isResponseInterruptible ? false : isLoading || !inputValue.trim()}
                    >
                      {isResponseInterruptible ? "Stop" : "Send"}
                    </button>
                  </div>
                </form>
              </div>

              <ChatInsightsPanel
                message={activeInsightMessage}
                onClose={() => setActiveInsightMessageId(null)}
              />
            </div>
          </div>
        </div>
        )}
      </div>
    </section>
  );
}

export default Dashboard;
