import { createContext, useContext, useMemo, useReducer } from 'react';

const CodeWorkspaceContext = createContext(null);

const initialState = {
  activeFileId: null,
  fileContents: {},
  chatHistory: [],
  aiResponses: [],
  executionLogs: [],
};

function reducer(state, action) {
  switch (action.type) {
    case 'SET_ACTIVE_FILE':
      return {
        ...state,
        activeFileId: action.payload || null,
      };
    case 'SYNC_FILE_CONTENT':
      return {
        ...state,
        fileContents: {
          ...state.fileContents,
          [action.payload.fileId]: action.payload.content,
        },
      };
    case 'PUSH_CHAT_MESSAGE':
      return {
        ...state,
        chatHistory: [action.payload, ...state.chatHistory].slice(0, 100),
      };
    case 'PUSH_AI_RESPONSE':
      return {
        ...state,
        aiResponses: [action.payload, ...state.aiResponses].slice(0, 100),
      };
    case 'PUSH_EXECUTION_LOG':
      return {
        ...state,
        executionLogs: [action.payload, ...state.executionLogs].slice(0, 100),
      };
    case 'CLEAR_EXECUTION_LOGS':
      return {
        ...state,
        executionLogs: [],
      };
    default:
      return state;
  }
}

export function CodeWorkspaceProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const actions = useMemo(
    () => ({
      setActiveFile(fileId) {
        dispatch({ type: 'SET_ACTIVE_FILE', payload: fileId });
      },
      syncFileContent(fileId, content) {
        dispatch({
          type: 'SYNC_FILE_CONTENT',
          payload: { fileId, content },
        });
      },
      pushChatMessage(message) {
        dispatch({ type: 'PUSH_CHAT_MESSAGE', payload: message });
      },
      pushAiResponse(response) {
        dispatch({ type: 'PUSH_AI_RESPONSE', payload: response });
      },
      pushExecutionLog(log) {
        dispatch({ type: 'PUSH_EXECUTION_LOG', payload: log });
      },
      clearExecutionLogs() {
        dispatch({ type: 'CLEAR_EXECUTION_LOGS' });
      },
    }),
    [],
  );

  const value = useMemo(
    () => ({ state, actions }),
    [state, actions],
  );

  return (
    <CodeWorkspaceContext.Provider value={value}>
      {children}
    </CodeWorkspaceContext.Provider>
  );
}

export function useCodeWorkspaceState() {
  const value = useContext(CodeWorkspaceContext);
  if (!value) {
    throw new Error('useCodeWorkspaceState must be used inside CodeWorkspaceProvider');
  }
  return value;
}
