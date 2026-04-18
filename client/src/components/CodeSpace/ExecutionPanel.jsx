/**
 * ExecutionPanel.jsx
 * Bottom panel for sandboxed code execution output and logs.
 */

import { useMemo, useState } from 'react';

function ExecutionPanel({
  activeFile,
  executionResult,
  executionError,
  isRunning,
  logs,
  onRun,
  onClearLogs,
}) {
  const [stdin, setStdin] = useState('');
  const [timeoutMs, setTimeoutMs] = useState(3000);

  const canRun = useMemo(() => {
    if (!activeFile || activeFile.is_folder || activeFile.isFolder) {
      return false;
    }
    return Boolean((activeFile.content || '').trim());
  }, [activeFile]);

  const handleRun = async () => {
    if (!canRun || !onRun) {
      return;
    }

    await onRun({
      stdin,
      timeoutMs,
    });
  };

  const result = executionResult?.result;

  return (
    <section className="execution-panel">
      <div className="execution-panel-header">
        <div className="execution-panel-title-wrap">
          <h4>Output / Logs</h4>
          <span className="execution-panel-file">
            {activeFile ? `${activeFile.filename} (${activeFile.language})` : 'No file selected'}
          </span>
        </div>

        <div className="execution-panel-actions">
          <input
            className="execution-timeout-input"
            type="number"
            min={200}
            max={30000}
            step={100}
            value={timeoutMs}
            onChange={(e) => setTimeoutMs(Number(e.target.value) || 3000)}
            title="Execution timeout in milliseconds"
          />
          <button
            className="execution-run-btn"
            onClick={handleRun}
            disabled={!canRun || isRunning}
          >
            {isRunning ? 'Running...' : 'Run'}
          </button>
          <button
            className="execution-clear-btn"
            onClick={onClearLogs}
            disabled={!logs?.length}
          >
            Clear Logs
          </button>
        </div>
      </div>

      <div className="execution-panel-controls">
        <label htmlFor="execution-stdin">Stdin (optional)</label>
        <textarea
          id="execution-stdin"
          className="execution-stdin"
          value={stdin}
          onChange={(e) => setStdin(e.target.value)}
          rows={2}
          placeholder="Enter input for your program"
        />
      </div>

      {(executionError || result?.stderr) && (
        <div className="execution-error-block">
          <pre>{executionError || result?.stderr}</pre>
        </div>
      )}

      {result && (
        <div className="execution-result-block">
          <div className="execution-result-meta">
            <span>Exit: {result.exit_code ?? 'n/a'}</span>
            <span>Runtime: {result.runtime_ms || 0}ms</span>
            <span>{result.timed_out ? 'Timed out' : 'Completed'}</span>
            {result.output_truncated && <span>Output truncated</span>}
          </div>
          <pre className="execution-stdout">{result.stdout || '(no stdout)'}</pre>
        </div>
      )}

      <div className="execution-logs">
        <h5>Recent Execution Events</h5>
        {!logs?.length ? (
          <p className="execution-empty">No execution logs yet.</p>
        ) : (
          <ul>
            {logs.map((log, index) => (
              <li key={`${log.timestamp}-${index}`}>
                <span>{new Date(log.timestamp).toLocaleTimeString()}</span>
                <span>{log.message}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export default ExecutionPanel;
