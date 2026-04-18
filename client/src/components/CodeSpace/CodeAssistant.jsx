/**
 * CodeAssistant.jsx
 * Right panel AI assistant for code help with RAG integration.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import useCodeAssist from '../../hooks/useCodeAssist';

function CodeAssistant({ activeFile, isLoading, onApplyCode, onInteraction }) {
  const [prompt, setPrompt] = useState('');
  const [action, setAction] = useState('explain');
  const [messages, setMessages] = useState([]);
  
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  
  const {
    isLoading: isAssistLoading,
    response,
    error,
    assist,
    clearResponse,
  } = useCodeAssist();

  // Scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Handle submit
  const handleSubmit = useCallback(async (e) => {
    e.preventDefault();
    
    if (!prompt.trim()) return;
    
    // Add user message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: prompt,
      action,
    };
    
    setMessages(prev => [...prev, userMessage]);
    onInteraction?.({ type: 'user', payload: userMessage });
    
    // Get AI response
    const result = await assist({
      code: activeFile?.content || '',
      language: activeFile?.language || 'javascript',
      prompt,
      action,
    });
    
    // Add AI message
    if (result) {
      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: result.explanation,
        improvedCode: result.updated_code || result.improved_code,
        suggestions: result.suggestions,
        contextUsed: result.context_used,
        contextSources: result.context_sources,
        warnings: result.warnings || [],
      };
      
      setMessages(prev => [...prev, aiMessage]);
      onInteraction?.({ type: 'assistant', payload: aiMessage });
    }
    
    setPrompt('');
  }, [prompt, action, activeFile, assist]);

  // Quick action buttons
  const handleQuickAction = useCallback((quickAction) => {
    setAction(quickAction);
    const prompts = {
      explain: 'Explain this code',
      fix: 'Find and fix any issues',
      refactor: 'Improve code quality and performance',
    };
    setPrompt(prompts[quickAction] || '');
    inputRef.current?.focus();
  }, []);

  // Apply improved code
  const handleApplyCode = useCallback((code) => {
    if (activeFile && code && typeof onApplyCode === 'function') {
      onApplyCode(code);
    }
  }, [activeFile, onApplyCode]);

  return (
    <div className="code-assistant">
      {/* Header */}
      <div className="code-assistant-header">
        <select
          className="code-assist-action-select"
          value={action}
          onChange={(e) => setAction(e.target.value)}
        >
          <option value="explain">Explain</option>
          <option value="generate">Generate</option>
          <option value="fix">Fix Bugs</option>
          <option value="refactor">Refactor</option>
        </select>
        
        <div className="code-assistant-context-badge">
          {activeFile ? activeFile.language : 'No file'}
        </div>
      </div>

      {/* Quick Actions */}
      <div className="code-assistant-quick-actions">
        <button
          className={`quick-action-btn ${action === 'explain' ? 'active' : ''}`}
          onClick={() => handleQuickAction('explain')}
        >
          Explain
        </button>
        <button
          className={`quick-action-btn ${action === 'fix' ? 'active' : ''}`}
          onClick={() => handleQuickAction('fix')}
        >
          Fix Bugs
        </button>
        <button
          className={`quick-action-btn ${action === 'refactor' ? 'active' : ''}`}
          onClick={() => handleQuickAction('refactor')}
        >
          Refactor
        </button>
      </div>

      {/* Messages */}
      <div className="code-assistant-messages">
        {messages.length === 0 ? (
          <div className="code-assistant-welcome">
            <h4>AI Code Assistant</h4>
            <p>Ask me to explain, generate, fix, or refactor code.</p>
            {activeFile?.content && (
              <p className="code-assistant-context-hint">
                I have access to your current file and knowledge context.
              </p>
            )}
          </div>
        ) : (
          messages.map((message) => (
            <div
              key={message.id}
              className={`code-assistant-message ${message.role}`}
            >
              <div className="message-header">
                <span className="message-role">
                  {message.role === 'user' ? 'You' : 'Intellexa'}
                </span>
                {message.contextUsed && (
                  <span className="context-badge" title="Used knowledge context">
                    Context Used
                  </span>
                )}
              </div>
              
              <div className="message-content">
                {message.content}
              </div>
              
              {message.improvedCode && (
                <div className="improved-code-section">
                  <div className="improved-code-header">
                    <span>Improved Code</span>
                    <button
                      className="apply-code-btn"
                      onClick={() => handleApplyCode(message.improvedCode)}
                    >
                      Apply
                    </button>
                  </div>
                  <pre className="improved-code">
                    <code>{message.improvedCode}</code>
                  </pre>
                </div>
              )}
              
              {message.suggestions?.length > 0 && (
                <div className="suggestions-section">
                  <span className="suggestions-title">Suggestions</span>
                  <ul className="suggestions-list">
                    {message.suggestions.map((s, i) => (
                      <li key={i}>
                        <strong>{s.title}</strong>
                        {s.description && <p>{s.description}</p>}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {message.warnings?.length > 0 && (
                <div className="suggestions-section">
                  <span className="suggestions-title">Warnings</span>
                  <ul className="suggestions-list">
                    {message.warnings.map((warning, i) => (
                      <li key={`warning-${i}`}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))
        )}
        
        {isAssistLoading && (
          <div className="code-assistant-loading">
            <span>Thinking...</span>
          </div>
        )}
        
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form className="code-assistant-input-form" onSubmit={handleSubmit}>
        <textarea
          ref={inputRef}
          className="code-assistant-input"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Ask about your code..."
          rows={2}
          disabled={isAssistLoading}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />
        <button
          type="submit"
          className="code-assistant-submit"
          disabled={isAssistLoading || !prompt.trim()}
        >
          {isAssistLoading ? '...' : 'Send'}
        </button>
      </form>

      {/* Error */}
      {error && (
        <div className="code-assistant-error">
          {error}
          <button onClick={clearResponse}>Dismiss</button>
        </div>
      )}
    </div>
  );
}

export default CodeAssistant;
