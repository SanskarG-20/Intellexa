/**
 * useCodeExecution.js
 * Hook for sandboxed code execution requests.
 */

import { useCallback, useState } from 'react';
import { executeCode } from '../services/codeFileService';

export function useCodeExecution() {
  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const runCode = useCallback(async (request) => {
    setIsRunning(true);
    setError(null);

    try {
      const response = await executeCode({
        code: request.code,
        language: request.language,
        stdin: request.stdin,
        timeoutMs: request.timeoutMs,
      });

      setResult(response);
      if (!response?.success && response?.error) {
        setError(response.error);
      }

      return response;
    } catch (err) {
      const message = err?.message || 'Execution failed.';
      setError(message);
      const fallback = {
        success: false,
        result: {
          stdout: '',
          stderr: message,
          exit_code: null,
          timed_out: false,
          runtime_ms: 0,
          output_truncated: false,
        },
        error: message,
      };
      setResult(fallback);
      return fallback;
    } finally {
      setIsRunning(false);
    }
  }, []);

  const clearResult = useCallback(() => {
    setResult(null);
    setError(null);
  }, []);

  return {
    isRunning,
    result,
    error,
    runCode,
    clearResult,
  };
}

export default useCodeExecution;
