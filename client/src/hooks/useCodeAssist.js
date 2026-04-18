/**
 * useCodeAssist.js
 * React hook for AI code assistance.
 */

import { useState, useCallback } from 'react';
import * as codeFileService from '../services/codeFileService';

/**
 * Available code assist actions
 */
export const CodeAction = {
  EXPLAIN: 'explain',
  GENERATE: 'generate',
  FIX: 'fix',
  REFACTOR: 'refactor',
  LEARN: 'learn',
};

/**
 * Custom hook for AI code assistance
 */
export function useCodeAssist() {
  const [isLoading, setIsLoading] = useState(false);
  const [response, setResponse] = useState(null);
  const [error, setError] = useState(null);
  const [history, setHistory] = useState([]);

  /**
   * Request code assistance
   */
  const assist = useCallback(async (request) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const result = await codeFileService.codeAssist({
        code: request.code || '',
        language: request.language || 'javascript',
        prompt: request.prompt,
        action: request.action || CodeAction.EXPLAIN,
        includeContext: request.includeContext !== false,
        context: request.context,
        learningMode: request.learningMode === true,
        maxSuggestions: request.maxSuggestions || 5,
      });
      
      setResponse(result);
      
      // Add to history
      setHistory(prev => [
        {
          id: Date.now(),
          request,
          response: result,
          timestamp: new Date().toISOString(),
        },
        ...prev.slice(0, 49), // Keep last 50 items
      ]);
      
      return result;
    } catch (err) {
      console.error('[CodeAssist] Failed:', err);
      setError(err.message);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * Explain code
   */
  const explain = useCallback(async (code, language) => {
    return assist({
      code,
      language,
      prompt: 'Explain what this code does',
      action: CodeAction.EXPLAIN,
    });
  }, [assist]);

  /**
   * Generate code from description
   */
  const generate = useCallback(async (prompt, language = 'javascript') => {
    return assist({
      code: '',
      language,
      prompt,
      action: CodeAction.GENERATE,
    });
  }, [assist]);

  /**
   * Fix bugs in code
   */
  const fix = useCallback(async (code, language, issue = '') => {
    return assist({
      code,
      language,
      prompt: issue || 'Find and fix any bugs or issues in this code',
      action: CodeAction.FIX,
    });
  }, [assist]);

  /**
   * Refactor code
   */
  const refactor = useCallback(async (code, language, goals = '') => {
    return assist({
      code,
      language,
      prompt: goals || 'Improve code quality, readability, and performance',
      action: CodeAction.REFACTOR,
    });
  }, [assist]);

  /**
   * Learning Mode deep explanation
   */
  const learn = useCallback(async (code, language, prompt = '') => {
    return assist({
      code,
      language,
      prompt: prompt || 'Explain this code deeply for learning',
      action: CodeAction.EXPLAIN,
      learningMode: true,
    });
  }, [assist]);

  /**
   * Clear the current response
   */
  const clearResponse = useCallback(() => {
    setResponse(null);
    setError(null);
  }, []);

  /**
   * Clear history
   */
  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  return {
    isLoading,
    response,
    error,
    history,
    assist,
    explain,
    generate,
    fix,
    refactor,
    learn,
    clearResponse,
    clearHistory,
  };
}

export default useCodeAssist;
