import React, { useState, useEffect, useRef } from 'react';
import { Search, Terminal, Mic, FolderOpen, Trash2, Moon, Database, LogOut } from 'lucide-react';

const COMMANDS = [
  { id: 'toggle_voice', label: 'Toggle Voice Mode', icon: Mic, description: 'Start hands-free voice conversation' },
  { id: 'toggle_layout', label: 'Toggle CodeSpace', icon: Terminal, description: 'Show or hide the code editor layout' },
  { id: 'toggle_sidebar', label: 'Toggle Sidebar', icon: FolderOpen, description: 'Show or hide the chat history sidebar' },
  { id: 'clear_chat', label: 'Clear Chat History', icon: Trash2, description: 'Reset the current chat session' },
  { id: 'switch_theme', label: 'Switch Theme', icon: Moon, description: 'Toggle between dark and light editor theme' },
  { id: 'open_kb', label: 'Open Knowledge Base', icon: Database, description: 'Manage project memory and files' },
  { id: 'sign_out', label: 'Sign Out', icon: LogOut, description: 'Sign out of Intellexa' },
];

export default function GlobalCommandPalette({ isOpen, onClose, onSelectAction }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef(null);

  const filteredCommands = COMMANDS.filter(cmd => 
    cmd.label.toLowerCase().includes(searchQuery.toLowerCase()) || 
    cmd.description.toLowerCase().includes(searchQuery.toLowerCase())
  );

  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => (prev + 1) % filteredCommands.length);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => (prev - 1 + filteredCommands.length) % filteredCommands.length);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          onSelectAction(filteredCommands[selectedIndex].id);
          onClose();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, filteredCommands, selectedIndex, onClose, onSelectAction]);

  if (!isOpen) return null;

  return (
    <div className="command-palette-overlay" onClick={onClose}>
      <div className="command-palette-modal" onClick={e => e.stopPropagation()}>
        <div className="command-palette-header">
          <Search className="command-palette-search-icon" size={20} />
          <input
            ref={inputRef}
            type="text"
            className="command-palette-input"
            placeholder="Search commands... (e.g., 'Voice')"
            value={searchQuery}
            onChange={e => {
              setSearchQuery(e.target.value);
              setSelectedIndex(0);
            }}
          />
          <kbd className="command-palette-esc">ESC</kbd>
        </div>
        <div className="command-palette-list">
          {filteredCommands.length === 0 ? (
            <div className="command-palette-empty">No commands found.</div>
          ) : (
            filteredCommands.map((cmd, index) => {
              const Icon = cmd.icon;
              return (
                <div
                  key={cmd.id}
                  className={`command-palette-item ${index === selectedIndex ? 'is-selected' : ''}`}
                  onClick={() => {
                    onSelectAction(cmd.id);
                    onClose();
                  }}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  <div className="command-palette-item-icon">
                    <Icon size={18} />
                  </div>
                  <div className="command-palette-item-content">
                    <div className="command-palette-item-title">{cmd.label}</div>
                    <div className="command-palette-item-desc">{cmd.description}</div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
