/**
 * CommandPalette — ⌘K fuzzy command launcher
 *
 * Registered commands: navigate sections, run diagnostics, ask Athena,
 * toggle voice, open prediction DB, export data.
 *
 * Global keyboard: ⌘K / Ctrl+K opens palette.
 * Usage: mount once in AppLayout; driven by uiStore.
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useNavigate }    from 'react-router-dom';
import { useUiStore }     from '@store/uiStore';
import { NAV_SECTIONS }   from '@types-athena';
import styles             from './CommandPalette.module.css';

// ── Command registry ──────────────────────────────────────────────────────────

interface Command {
  id:       string;
  label:    string;
  icon:     string;
  group:    string;
  keywords: string[];
  action:   () => void;
}

function useCommands() {
  const navigate     = useNavigate();
  const openAthena   = useUiStore(s => s.openAthenaPanel);
  const notify       = useUiStore(s => s.notify);

  const commands = useMemo<Command[]>(() => [
    // Navigation
    ...NAV_SECTIONS.map(s => ({
      id:       `nav-${s.id}`,
      label:    `Go to ${s.label}`,
      icon:     s.icon,
      group:    'Navigate',
      keywords: [s.label.toLowerCase(), s.id],
      action:   () => navigate(`/${s.id}`),
    })),
    // Actions
    {
      id:       'ask-athena',
      label:    'Ask Athena…',
      icon:     '⚡',
      group:    'AI',
      keywords: ['ask', 'athena', 'ai', 'question', 'help'],
      action:   () => openAthena(''),
    },
    {
      id:       'run-diagnostics',
      label:    'Run Diagnostics',
      icon:     '🔬',
      group:    'Actions',
      keywords: ['run', 'diag', 'diagnostics', 'analyze'],
      action:   () => {
        navigate('/overview');
        notify({ level: 'info', title: 'Diagnostics', message: 'Opening diagnostic runner…', ttl: 3000 });
      },
    },
    {
      id:       'export-csv',
      label:    'Export Picks as CSV',
      icon:     '📥',
      group:    'Actions',
      keywords: ['export', 'csv', 'download', 'picks'],
      action:   () => {
        window.location.assign('/api/diagnostics/export');
      },
    },
    {
      id:       'open-prediction-db',
      label:    'Open Prediction DB',
      icon:     '🗄️',
      group:    'Navigate',
      keywords: ['prediction', 'database', 'picks', 'archive'],
      action:   () => navigate('/prediction-db'),
    },
    {
      id:       'open-roadmap',
      label:    'Open Roadmap',
      icon:     '🚀',
      group:    'Navigate',
      keywords: ['roadmap', 'plan', 'todo', 'tasks'],
      action:   () => navigate('/roadmap'),
    },
    {
      id:       'calibration-analysis',
      label:    'Ask Athena: Explain Calibration',
      icon:     '🎯',
      group:    'AI',
      keywords: ['calibration', 'brier', 'ece', 'explain'],
      action:   () => openAthena('Explain the model\'s current calibration status and what we should do about it.'),
    },
    {
      id:       'edge-analysis',
      label:    'Ask Athena: Analyze Edge',
      icon:     '💰',
      group:    'AI',
      keywords: ['edge', 'ev', 'expected value', 'analyze'],
      action:   () => openAthena('Is the model\'s EV signal monotonically predictive? What\'s the highest-value action to take right now?'),
    },
    {
      id:       'explain-loss',
      label:    'Ask Athena: Explain Recent Losses',
      icon:     '🔍',
      group:    'AI',
      keywords: ['loss', 'losses', 'explain', 'bad', 'wrong'],
      action:   () => openAthena('What are the top 3 reasons for recent losses? What patterns do you see in the losing picks?'),
    },
    {
      id:       'weekly-summary',
      label:    'Ask Athena: Weekly Research Summary',
      icon:     '📋',
      group:    'AI',
      keywords: ['weekly', 'summary', 'report', 'week'],
      action:   () => openAthena('Give me a weekly research summary: what worked, what didn\'t, and what to focus on next week.'),
    },
  ], [navigate, openAthena, notify]);

  return commands;
}

// ── Fuzzy match ───────────────────────────────────────────────────────────────

function fuzzyScore(query: string, command: Command): number {
  const q = query.toLowerCase();
  const label = command.label.toLowerCase();
  const keywords = command.keywords.join(' ');

  if (label.startsWith(q)) return 100;
  if (label.includes(q))   return 80;
  if (keywords.includes(q)) return 60;

  // Character-by-character fuzzy
  let score = 0;
  let ki    = 0;
  for (const ch of q) {
    const idx = label.indexOf(ch, ki);
    if (idx >= 0) { score += 1; ki = idx + 1; }
  }
  return score > q.length * 0.6 ? score * 10 : 0;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function CommandPalette() {
  const [open,    setOpen]    = useState(false);
  const [query,   setQuery]   = useState('');
  const [cursor,  setCursor]  = useState(0);
  const inputRef              = useRef<HTMLInputElement>(null);
  const commands              = useCommands();

  // Global ⌘K / Ctrl+K
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(o => !o);
        setQuery('');
        setCursor(0);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Focus input when opened
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  const close = useCallback(() => { setOpen(false); setQuery(''); }, []);

  // Filtered + sorted results
  const results = useMemo(() => {
    if (!query.trim()) {
      // Show all grouped by section, limit 12
      return commands.slice(0, 12);
    }
    return commands
      .map(c => ({ command: c, score: fuzzyScore(query, c) }))
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map(x => x.command)
      .slice(0, 10);
  }, [query, commands]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)); }
    if (e.key === 'ArrowUp')   { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)); }
    if (e.key === 'Enter') {
      const cmd = results[cursor];
      if (cmd) { cmd.action(); close(); }
    }
    if (e.key === 'Escape') close();
  };

  // Group results for display
  const grouped = useMemo(() => {
    const groups: Record<string, Command[]> = {};
    for (const cmd of results) {
      if (!groups[cmd.group]) groups[cmd.group] = [];
      groups[cmd.group].push(cmd);
    }
    return groups;
  }, [results]);

  let globalIdx = 0;

  if (!open) return null;

  return (
    <div className={styles.overlay} onClick={close} role="presentation">
      <div
        className={styles.palette}
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label="Command palette"
      >
        {/* Search input */}
        <div className={styles.searchRow}>
          <span className={styles.searchIcon} aria-hidden>⌘</span>
          <input
            ref={inputRef}
            className={styles.input}
            placeholder="Search commands…"
            value={query}
            onChange={e => { setQuery(e.target.value); setCursor(0); }}
            onKeyDown={handleKeyDown}
            aria-label="Command search"
            aria-autocomplete="list"
            spellCheck={false}
          />
          <kbd className={styles.escKbd}>ESC</kbd>
        </div>

        {/* Results */}
        <div className={styles.results} role="listbox">
          {results.length === 0 ? (
            <div className={styles.empty}>No commands found for "{query}"</div>
          ) : (
            Object.entries(grouped).map(([group, cmds]) => (
              <div key={group} className={styles.group}>
                <div className={styles.groupLabel}>{group}</div>
                {cmds.map(cmd => {
                  const idx      = globalIdx++;
                  const isActive = idx === cursor;
                  return (
                    <button
                      key={cmd.id}
                      className={[styles.item, isActive ? styles.active : ''].join(' ')}
                      onClick={() => { cmd.action(); close(); }}
                      onMouseEnter={() => setCursor(idx)}
                      role="option"
                      aria-selected={isActive}
                    >
                      <span className={styles.itemIcon} aria-hidden>{cmd.icon}</span>
                      <span className={styles.itemLabel}>{cmd.label}</span>
                      {isActive && <kbd className={styles.enterKbd}>↵</kbd>}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div className={styles.footer}>
          <span><kbd>↑↓</kbd> navigate</span>
          <span><kbd>↵</kbd> select</span>
          <span><kbd>Esc</kbd> close</span>
          <span><kbd>⌘K</kbd> toggle</span>
        </div>
      </div>
    </div>
  );
}
