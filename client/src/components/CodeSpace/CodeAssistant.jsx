/**
 * CodeAssistant.jsx
 * Right panel AI assistant for code help with RAG integration.
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import useCodeAssist from '../../hooks/useCodeAssist';

function CodeAssistant({ activeFile, isLoading, onApplyCode, onInteraction }) {
  const [prompt, setPrompt] = useState('');
  const [action, setAction] = useState('explain');
  const [learningMode, setLearningMode] = useState(false);
  const [taskMode, setTaskMode] = useState(false);
  const [whyBrokeMode, setWhyBrokeMode] = useState(false);
  const [taskSessionId, setTaskSessionId] = useState(null);
  const [taskPrompt, setTaskPrompt] = useState('');
  const [taskCompletedStepIds, setTaskCompletedStepIds] = useState([]);
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

    const normalizedPrompt = prompt.trim();
    const shouldRegenerateTaskPlan = (
      taskMode
      && Boolean(taskSessionId)
      && Boolean(taskPrompt)
      && normalizedPrompt !== taskPrompt
    );
    const completedStepIds = shouldRegenerateTaskPlan ? [] : taskCompletedStepIds;
    
    // Add user message
    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: normalizedPrompt,
      action,
      learningMode,
      taskMode,
      whyBrokeMode,
    };
    
    setMessages(prev => [...prev, userMessage]);
    onInteraction?.({ type: 'user', payload: userMessage });
    
    // Get AI response
    const result = await assist({
      code: activeFile?.content || '',
      language: activeFile?.language || 'javascript',
      prompt: normalizedPrompt,
      action,
      learningMode,
      taskMode,
      fileId: activeFile?.id,
      versionIntelligence: whyBrokeMode,
      taskSessionId,
      completedStepIds,
      regeneratePlan: shouldRegenerateTaskPlan,
    });
    
    // Add AI message
    if (result) {
      if (result.task_mode) {
        const completedIds = (result.steps || [])
          .filter((step) => step.status === 'completed')
          .map((step) => step.id);

        setTaskMode(true);
        setLearningMode(false);
        setAction('task');
        setTaskSessionId(result.task_session_id || null);
        setTaskPrompt(normalizedPrompt);
        setTaskCompletedStepIds(completedIds);
      }

      const aiMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: result.task_mode
          ? (result.summary || result.title || 'Task plan created.')
          : result.explanation,
        improvedCode: result.updated_code || result.improved_code,
        suggestions: result.suggestions,
        contextUsed: result.context_used,
        contextSources: result.context_sources,
        learningMode: result.learning_mode,
        learningExplanation: result.learning_explanation,
        taskMode: result.task_mode === true,
        taskSessionId: result.task_session_id,
        taskTitle: result.title,
        taskSummary: result.summary,
        taskSteps: result.steps || [],
        taskProgress: result.progress,
        versionIntelligence: result.version_intelligence === true,
        breakCauses: result.break_causes || [],
        versionCompare: result.version_compare || null,
        warnings: result.warnings || [],
      };
      
      setMessages(prev => [...prev, aiMessage]);
      onInteraction?.({ type: 'assistant', payload: aiMessage });
    }
    
    setPrompt('');
  }, [
    prompt,
    action,
    learningMode,
    taskMode,
    whyBrokeMode,
    taskSessionId,
    taskPrompt,
    taskCompletedStepIds,
    activeFile,
    assist,
    onInteraction,
  ]);

  const handleTaskStepComplete = useCallback(async (stepId) => {
    if (!stepId || !taskSessionId || !taskPrompt) {
      return;
    }

    const completedStepIds = Array.from(new Set([...taskCompletedStepIds, stepId]));
    setTaskCompletedStepIds(completedStepIds);

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: `Mark ${stepId} as completed`,
      action: 'task',
      taskMode: true,
    };
    setMessages((prev) => [...prev, userMessage]);
    onInteraction?.({ type: 'user', payload: userMessage });

    const result = await assist({
      code: activeFile?.content || '',
      language: activeFile?.language || 'javascript',
      prompt: taskPrompt,
      action: 'task',
      taskMode: true,
      taskSessionId,
      completedStepIds,
    });

    if (!result || !result.task_mode) {
      return;
    }

    const normalizedCompletedIds = (result.steps || [])
      .filter((step) => step.status === 'completed')
      .map((step) => step.id);
    setTaskSessionId(result.task_session_id || taskSessionId);
    setTaskCompletedStepIds(normalizedCompletedIds);

    const aiMessage = {
      id: Date.now() + 1,
      role: 'assistant',
      content: result.summary || result.title || 'Task progress updated.',
      taskMode: true,
      taskSessionId: result.task_session_id,
      taskTitle: result.title,
      taskSummary: result.summary,
      taskSteps: result.steps || [],
      taskProgress: result.progress,
      contextUsed: result.context_used,
      contextSources: result.context_sources,
      warnings: result.warnings || [],
      suggestions: [],
    };
    setMessages((prev) => [...prev, aiMessage]);
    onInteraction?.({ type: 'assistant', payload: aiMessage });
  }, [
    taskSessionId,
    taskPrompt,
    taskCompletedStepIds,
    assist,
    activeFile,
    onInteraction,
  ]);

  // Quick action buttons
  const handleQuickAction = useCallback((quickAction) => {
    if (quickAction === 'learning') {
      setAction('explain');
      setLearningMode(true);
      setTaskMode(false);
      setWhyBrokeMode(false);
    } else if (quickAction === 'task') {
      setAction('task');
      setLearningMode(false);
      setTaskMode(true);
      setWhyBrokeMode(false);
    } else if (quickAction === 'why_broke') {
      setAction('why_broke');
      setLearningMode(false);
      setTaskMode(false);
      setWhyBrokeMode(true);
    } else {
      setAction(quickAction);
      setLearningMode(false);
      setTaskMode(false);
      setWhyBrokeMode(false);
    }

    const prompts = {
      explain: 'Explain this code',
      fix: 'Find and fix any issues',
      refactor: 'Improve code quality and performance',
      learning: 'Teach me this code step-by-step with logic breakdown and analogy',
      task: 'Build a feature',
      why_broke: 'Why did this break?',
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
          onChange={(e) => {
            const next = e.target.value;
            setAction(next);
            setTaskMode(next === 'task');
            setWhyBrokeMode(next === 'why_broke');
            if (next !== 'explain') {
              setLearningMode(false);
            }
            if (next === 'task') {
              setLearningMode(false);
            }
            if (next === 'why_broke') {
              setLearningMode(false);
              setTaskMode(false);
            }
          }}
        >
          <option value="explain">Explain</option>
          <option value="generate">Generate</option>
          <option value="fix">Fix Bugs</option>
          <option value="refactor">Refactor</option>
          <option value="task">Task Builder</option>
          <option value="why_broke">Why Broke?</option>
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
        <button
          className={`quick-action-btn ${learningMode ? 'active' : ''}`}
          onClick={() => handleQuickAction('learning')}
        >
          Learning
        </button>
        <button
          className={`quick-action-btn ${taskMode ? 'active' : ''}`}
          onClick={() => handleQuickAction('task')}
        >
          Task Builder
        </button>
        <button
          className={`quick-action-btn ${whyBrokeMode ? 'active' : ''}`}
          onClick={() => handleQuickAction('why_broke')}
        >
          Why Broke?
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

              {message.taskMode && message.taskSteps?.length > 0 && (
                <div className="suggestions-section">
                  <span className="suggestions-title">
                    {message.taskTitle || 'Project Builder Plan'}
                  </span>
                  {message.taskSummary && (
                    <p className="task-mode-summary">{message.taskSummary}</p>
                  )}
                  {message.taskProgress && (
                    <p className="task-mode-progress">
                      Progress: {message.taskProgress.completed_steps}/{message.taskProgress.total_steps}
                      {' '}
                      ({message.taskProgress.completion_percent}%)
                    </p>
                  )}

                  <ul className="suggestions-list">
                    {message.taskSteps.map((step) => (
                      <li key={step.id}>
                        <strong>{step.title}</strong>
                        {step.description && <p>{step.description}</p>}
                        <p className="task-mode-status">Status: {step.status}</p>

                        {step.code && (
                          <pre className="improved-code">
                            <code>{step.code}</code>
                          </pre>
                        )}

                        {step.acceptance_criteria?.length > 0 && (
                          <p className="task-mode-criteria">
                            Acceptance: {step.acceptance_criteria.join(' | ')}
                          </p>
                        )}

                        {step.status !== 'completed' && message.taskSessionId && (
                          <button
                            className="apply-code-btn"
                            disabled={isAssistLoading}
                            onClick={() => handleTaskStepComplete(step.id)}
                          >
                            Mark Step Complete
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {message.versionIntelligence && (
                <div className="suggestions-section">
                  <span className="suggestions-title">Version Intelligence</span>

                  {message.versionCompare && (
                    <p className="task-mode-progress">
                      {message.versionCompare.summary}
                    </p>
                  )}

                  {message.breakCauses?.length > 0 && (
                    <ul className="suggestions-list">
                      {message.breakCauses.map((cause, idx) => (
                        <li key={`cause-${idx}`}>
                          <strong>
                            {cause.title}
                            {typeof cause.confidence === 'number' ? ` (${Math.round(cause.confidence * 100)}%)` : ''}
                          </strong>
                          {cause.evidence && <p>{cause.evidence}</p>}
                          {cause.recommendation && <p>{cause.recommendation}</p>}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {message.learningMode && message.learningExplanation && (
                <div className="suggestions-section">
                  <span className="suggestions-title">Step-by-Step Explanation</span>
                  <ul className="suggestions-list">
                    {(message.learningExplanation.step_by_step || []).map((step, i) => (
                      <li key={`learn-step-${i}`}>{step}</li>
                    ))}
                  </ul>

                  <span className="suggestions-title">Logic Breakdown</span>
                  <ul className="suggestions-list">
                    {(message.learningExplanation.logic_breakdown || []).map((item, i) => (
                      <li key={`learn-logic-${i}`}>{item}</li>
                    ))}
                  </ul>

                  <span className="suggestions-title">Real-World Analogy</span>
                  <p>{message.learningExplanation.real_world_analogy}</p>
                </div>
              )}
              
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
          placeholder={
            taskMode
              ? 'Describe the feature to build...'
              : whyBrokeMode
                ? 'Describe the breakage or paste the error...'
              : learningMode
                ? 'Ask for a deep teaching explanation...'
                : 'Ask about your code...'
          }
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
