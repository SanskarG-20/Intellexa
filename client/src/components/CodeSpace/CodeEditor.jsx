/**
 * CodeEditor.jsx
 * Monaco Editor wrapper with syntax highlighting and AI autocomplete.
 */

import { useRef, useCallback, useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { codeAutocomplete } from '../../services/codeFileService';

const EDITOR_THEMES = {
  dark: 'vs-dark',
  light: 'light',
};

function mapMonacoLanguage(language) {
  const languageMap = {
    javascript: 'javascript',
    typescript: 'typescript',
    python: 'python',
    html: 'html',
    css: 'css',
    scss: 'scss',
    json: 'json',
    markdown: 'markdown',
    yaml: 'yaml',
    xml: 'xml',
    sql: 'sql',
    bash: 'shell',
    java: 'java',
    go: 'go',
    rust: 'rust',
    c: 'c',
    cpp: 'cpp',
    csharp: 'csharp',
    php: 'php',
    ruby: 'ruby',
  };

  return languageMap[language] || 'plaintext';
}

function CodeEditor({
  file,
  onChange,
  onSave,
  onRunCode,
  isLoading,
}) {
  const editorRef = useRef(null);
  const monacoRef = useRef(null);
  const completionProviderRef = useRef(null);
  const autocompleteTimerRef = useRef(null);
  const pendingAutocompleteResolverRef = useRef(null);

  const [theme, setTheme] = useState('dark');
  const [fontSize, setFontSize] = useState(14);
  const [minimap, setMinimap] = useState(true);

  const getDebouncedAutocomplete = useCallback((payload) => {
    return new Promise((resolve) => {
      if (pendingAutocompleteResolverRef.current) {
        pendingAutocompleteResolverRef.current({ suggestions: [] });
      }

      pendingAutocompleteResolverRef.current = resolve;

      if (autocompleteTimerRef.current) {
        clearTimeout(autocompleteTimerRef.current);
      }

      autocompleteTimerRef.current = setTimeout(async () => {
        try {
          const result = await codeAutocomplete(payload);
          resolve(result || { suggestions: [] });
        } catch {
          resolve({ suggestions: [] });
        } finally {
          pendingAutocompleteResolverRef.current = null;
        }
      }, 300);
    });
  }, []);

  const registerAutocompleteProvider = useCallback(() => {
    if (!monacoRef.current || !editorRef.current || !file) {
      return;
    }

    if (completionProviderRef.current) {
      completionProviderRef.current.dispose();
      completionProviderRef.current = null;
    }

    const monaco = monacoRef.current;
    const editor = editorRef.current;
    const monacoLanguage = mapMonacoLanguage(file.language);

    completionProviderRef.current = monaco.languages.registerCompletionItemProvider(
      monacoLanguage,
      {
        triggerCharacters: ['.', ':', '(', '{', '[', ','],
        provideCompletionItems: async (model, position) => {
          const response = await getDebouncedAutocomplete({
            code: model.getValue(),
            language: file.language,
            cursorLine: position.lineNumber,
            cursorColumn: position.column,
            maxSuggestions: 3,
          });

          const word = model.getWordUntilPosition(position);
          const replaceRange = {
            startLineNumber: position.lineNumber,
            endLineNumber: position.lineNumber,
            startColumn: word.startColumn,
            endColumn: word.endColumn,
          };

          const suggestions = (response?.suggestions || []).map((item, index) => ({
            label: item.label,
            kind: monaco.languages.CompletionItemKind.Snippet,
            insertText: item.insert_text,
            detail: item.detail || 'AI suggestion',
            range: replaceRange,
            sortText: `a${String(index).padStart(3, '0')}`,
          }));

          return { suggestions };
        },
      },
    );

    editor.trigger('intellexa', 'editor.action.inlineSuggest.trigger', {});
  }, [file, getDebouncedAutocomplete]);

  const handleEditorDidMount = useCallback((editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      onSave?.();
    });

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
      onRunCode?.();
    });

    editor.focus();
    registerAutocompleteProvider();
  }, [onRunCode, onSave, registerAutocompleteProvider]);

  const handleChange = useCallback((value) => {
    onChange?.(value);
  }, [onChange]);

  useEffect(() => {
    if (editorRef.current && file) {
      const model = editorRef.current.getModel();
      if (model) {
        const currentValue = model.getValue();
        if (currentValue !== file.content) {
          model.setValue(file.content || '');
        }
      }
    }
  }, [file?.id, file?.content]);

  useEffect(() => {
    registerAutocompleteProvider();
  }, [registerAutocompleteProvider, file?.id, file?.language]);

  useEffect(() => {
    return () => {
      if (completionProviderRef.current) {
        completionProviderRef.current.dispose();
      }
      if (autocompleteTimerRef.current) {
        clearTimeout(autocompleteTimerRef.current);
      }
      if (pendingAutocompleteResolverRef.current) {
        pendingAutocompleteResolverRef.current({ suggestions: [] });
      }
    };
  }, []);

  if (!file) {
    return (
      <div className="code-editor-empty">
        <div className="code-editor-empty-content">
          <h2>No file selected</h2>
          <p>Open a file from the explorer or create a new one</p>
          <div className="code-editor-shortcuts">
            <h4>Keyboard Shortcuts</h4>
            <ul>
              <li><kbd>Ctrl</kbd> + <kbd>S</kbd> - Save file</li>
              <li><kbd>Ctrl</kbd> + <kbd>Enter</kbd> - Run code</li>
              <li><kbd>Ctrl</kbd> + <kbd>W</kbd> - Close tab</li>
            </ul>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="code-editor-container">
      <div className="code-editor-toolbar">
        <div className="code-editor-toolbar-left">
          <span className="code-editor-filename">{file.filename}</span>
          <span className="code-editor-language">{file.language}</span>
        </div>
        <div className="code-editor-toolbar-right">
          <button
            className="code-editor-run-btn"
            onClick={onRunCode}
            title="Run (Ctrl/Cmd + Enter)"
          >
            Run
          </button>
          <select
            className="code-editor-theme-select"
            value={theme}
            onChange={(e) => setTheme(e.target.value)}
          >
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
          <select
            className="code-editor-font-select"
            value={fontSize}
            onChange={(e) => setFontSize(Number(e.target.value))}
          >
            {[12, 13, 14, 15, 16, 18, 20].map((size) => (
              <option key={size} value={size}>{size}px</option>
            ))}
          </select>
          <button
            className="code-editor-toolbar-btn"
            onClick={() => setMinimap(!minimap)}
            title={minimap ? 'Hide Minimap' : 'Show Minimap'}
          >
            {minimap ? '⊖' : '⊕'}
          </button>
        </div>
      </div>

      <Editor
        height="100%"
        language={mapMonacoLanguage(file.language)}
        theme={EDITOR_THEMES[theme]}
        value={file.content || ''}
        onChange={handleChange}
        onMount={handleEditorDidMount}
        loading={
          <div className="code-editor-loading">
            <span>Loading editor...</span>
          </div>
        }
        options={{
          fontSize,
          minimap: { enabled: minimap },
          scrollBeyondLastLine: false,
          automaticLayout: true,
          tabSize: 2,
          wordWrap: 'on',
          lineNumbers: 'on',
          folding: true,
          renderWhitespace: 'selection',
          bracketPairColorization: { enabled: true },
          suggest: {
            showKeywords: true,
            showSnippets: true,
          },
          quickSuggestions: {
            other: true,
            comments: false,
            strings: true,
          },
        }}
      />

      {isLoading && (
        <div className="code-editor-busy-overlay">
          <span>Syncing...</span>
        </div>
      )}
    </div>
  );
}

export default CodeEditor;
