/**
 * AthenaPanel — Sliding AI research assistant chat drawer
 *
 * Opens from the right when:
 *   - User clicks "Ask Athena" on any chart (pre-filled context)
 *   - User clicks "Ask Athena" in TopBar
 *   - Command palette triggers openAthenaPanel()
 *
 * Chat messages stream via /api/athena/chat (POST → SSE).
 * Falls back to a mock response if server doesn't support streaming.
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useUiStore }   from '@store/uiStore';
import { ConfidenceChip } from '@components/ConfidenceChip';
import styles           from './AthenaPanel.module.css';

// ── Types ─────────────────────────────────────────────────────────────────────

interface Message {
  id:        string;
  role:      'user' | 'athena';
  content:   string;
  timestamp: number;
  loading?:  boolean;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function uid() { return Math.random().toString(36).slice(2, 9); }

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

/** Render **bold** and `code` in Athena messages */
function renderMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>');
}

// ── Mock Athena responses for offline / no-backend mode ──────────────────────

const MOCK_RESPONSES: Record<string, string> = {
  default: "I'm analyzing the data from your picks database. Based on the current diagnostics, I can see the model has a **48.3% overall win rate** against a break-even of 52.4%. The most critical finding is the **21pp gap** between UNDER picks (62% WR) and OVER picks (41% WR). I'd recommend focusing on: 1) Filtering to UNDER-only for the next 30 picks, 2) Investigating park factor calibration, 3) Building a minimum 4% EV filter.",
  calibration: "The model's **Brier score of 0.244** vs a naive baseline of 0.250 represents only a 2.4% improvement — barely above noise. The key insight is that this isn't a calibration crisis yet, it's a **sample size problem**. With 60 picks, each probability bucket has fewer than 10 samples, making the reliability diagram unreliable. I'd recommend waiting until 200+ picks before investing in post-processing techniques like Platt scaling.",
  edge: "The EV signal shows **directional predictiveness** but not clean monotonicity. Higher EV buckets do tend to win more, but the relationship is noisy enough that I'd treat EV as a necessary but not sufficient condition for betting. The combination of **EV > 3% AND UNDER direction** is your highest-confidence filter based on current data.",
};

async function queryAthena(
  userMessage: string,
  onChunk: (chunk: string) => void,
  onDone: () => void,
): Promise<void> {
  try {
    const response = await fetch('/api/athena/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: userMessage }),
    });

    if (!response.ok || !response.body) throw new Error('No response body');

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      // Parse SSE lines
      for (const line of chunk.split('\n')) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data === '[DONE]') { onDone(); return; }
          try {
            const parsed = JSON.parse(data);
            if (parsed.content) onChunk(parsed.content);
          } catch { onChunk(data); }
        }
      }
    }
    onDone();
  } catch {
    // Offline mock — simulate streaming
    const mock = Object.entries(MOCK_RESPONSES).find(([k]) =>
      userMessage.toLowerCase().includes(k)
    )?.[1] ?? MOCK_RESPONSES.default;

    const words = mock.split(' ');
    for (let i = 0; i < words.length; i++) {
      await new Promise(r => setTimeout(r, 30 + Math.random() * 20));
      onChunk((i === 0 ? '' : ' ') + words[i]);
    }
    onDone();
  }
}

// ── Suggested prompts ─────────────────────────────────────────────────────────

const SUGGESTED_PROMPTS = [
  'Explain the OVER/UNDER win rate gap',
  'What should I fix first to improve ROI?',
  'Is the EV signal working?',
  'Analyze calibration and recommend action',
  'What experiments should I run next?',
  'Summarize today\'s model performance',
];

// ── Component ─────────────────────────────────────────────────────────────────

export function AthenaPanel() {
  const open      = useUiStore(s => s.athenaPanelOpen);
  const prefill   = useUiStore(s => s.athenaPanelQuery);
  const closePanel = useUiStore(s => s.closeAthenaPanel);

  const [messages,  setMessages]  = useState<Message[]>([]);
  const [input,     setInput]     = useState('');
  const [streaming, setStreaming] = useState(false);
  const bottomRef                 = useRef<HTMLDivElement>(null);
  const inputRef                  = useRef<HTMLTextAreaElement>(null);

  // Apply pre-filled query when panel opens
  useEffect(() => {
    if (open && prefill) {
      setInput(prefill);
      setTimeout(() => inputRef.current?.focus(), 100);
    } else if (open) {
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open, prefill]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = useCallback(async (text?: string) => {
    const content = (text ?? input).trim();
    if (!content || streaming) return;

    const userMsg: Message = { id: uid(), role: 'user', content, timestamp: Date.now() };
    const loadingMsg: Message = { id: uid(), role: 'athena', content: '', timestamp: Date.now(), loading: true };

    setMessages(prev => [...prev, userMsg, loadingMsg]);
    setInput('');
    setStreaming(true);

    await queryAthena(
      content,
      (chunk) => {
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (!last || last.role !== 'athena') return prev;
          return [...prev.slice(0, -1), { ...last, content: last.content + chunk, loading: false }];
        });
      },
      () => {
        setStreaming(false);
        setMessages(prev => {
          const last = prev[prev.length - 1];
          if (last?.loading) {
            return [...prev.slice(0, -1), { ...last, loading: false }];
          }
          return prev;
        });
      },
    );
  }, [input, streaming]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <>
      {/* Backdrop */}
      <div
        className={[styles.backdrop, open ? styles.backdropVisible : ''].join(' ')}
        onClick={closePanel}
        aria-hidden
      />

      {/* Panel */}
      <aside
        className={[styles.panel, open ? styles.open : ''].join(' ')}
        role="complementary"
        aria-label="Athena AI Research Assistant"
        aria-hidden={!open}
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.identity}>
            <div className={styles.avatar} aria-hidden>⚡</div>
            <div>
              <div className={styles.name}>Athena</div>
              <div className={styles.subtitle}>AI Research Assistant</div>
            </div>
          </div>
          <div className={styles.headerRight}>
            <ConfidenceChip value={87} label="Online" size="sm" showArc />
            <button className={styles.closeBtn} onClick={closePanel} aria-label="Close Athena">✕</button>
          </div>
        </div>

        {/* Messages */}
        <div className={styles.messages} role="log" aria-live="polite">
          {messages.length === 0 ? (
            <div className={styles.welcome}>
              <div className={styles.welcomeIcon} aria-hidden>⚡</div>
              <h3 className={styles.welcomeTitle}>Ask Athena</h3>
              <p className={styles.welcomeText}>
                I'm your AI research partner. Ask me to explain charts, diagnose model issues,
                suggest experiments, or summarize performance.
              </p>
              <div className={styles.suggestions}>
                {SUGGESTED_PROMPTS.map(prompt => (
                  <button
                    key={prompt}
                    className={styles.suggestion}
                    onClick={() => send(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map(msg => (
              <div
                key={msg.id}
                className={[styles.message, styles[msg.role]].join(' ')}
              >
                {msg.role === 'athena' && (
                  <div className={styles.msgAvatar} aria-hidden>⚡</div>
                )}
                <div className={styles.msgBubble}>
                  {msg.loading ? (
                    <div className={styles.typingDots}>
                      <span /><span /><span />
                    </div>
                  ) : (
                    <div
                      className={styles.msgContent}
                      dangerouslySetInnerHTML={{ __html: `<p>${renderMarkdown(msg.content)}</p>` }}
                    />
                  )}
                  <div className={styles.msgTime}>{formatTime(msg.timestamp)}</div>
                </div>
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className={styles.inputArea}>
          <div className={styles.inputWrap}>
            <textarea
              ref={inputRef}
              className={styles.input}
              placeholder="Ask Athena anything about your model…"
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={streaming}
              aria-label="Message Athena"
            />
            <button
              className={styles.sendBtn}
              onClick={() => send()}
              disabled={!input.trim() || streaming}
              aria-label="Send message"
            >
              {streaming ? '⋯' : '↑'}
            </button>
          </div>
          <div className={styles.inputHint}>
            <kbd>Enter</kbd> send · <kbd>Shift+Enter</kbd> new line
          </div>
        </div>
      </aside>
    </>
  );
}
