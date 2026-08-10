/**
 * stream.ts — Server-Sent Events handler for diagnostic run output
 *
 * Connects to /api/diagnostics/run, which streams newline-delimited
 * JSON objects: { line: string } | { done: true, code: number }
 *
 * Designed to be called from a React hook (useStream) — returns a
 * cleanup function for useEffect teardown.
 */

// ── Event shapes from Flask ───────────────────────────────────────────────────

interface StreamLineEvent {
  line: string;
}

interface StreamDoneEvent {
  done:  true;
  code:  number;
}

type StreamEvent = StreamLineEvent | StreamDoneEvent;

// ── Callbacks surface ─────────────────────────────────────────────────────────

export interface StreamCallbacks {
  onLine:       (line: string) => void;
  onDone:       (exitCode: number) => void;
  onError:      (error: Event) => void;
  onConnect?:   () => void;
}

// ── Stream controller ─────────────────────────────────────────────────────────

export interface StreamController {
  /** Call to manually close the SSE connection. */
  close: () => void;
  /** True while the SSE connection is open. */
  isOpen: () => boolean;
}

// ── Open a diagnostic run stream ──────────────────────────────────────────────

export function openDiagStream(callbacks: StreamCallbacks): StreamController {
  const url = '/api/diagnostics/run';
  const es  = new EventSource(url);
  let open  = true;

  es.addEventListener('open', () => {
    callbacks.onConnect?.();
  });

  es.addEventListener('message', (event: MessageEvent<string>) => {
    let parsed: StreamEvent;

    try {
      parsed = JSON.parse(event.data) as StreamEvent;
    } catch {
      // Malformed JSON — surface as a line so terminal shows it
      callbacks.onLine(`[parse error] ${event.data}`);
      return;
    }

    if ('done' in parsed && parsed.done) {
      open = false;
      es.close();
      callbacks.onDone(parsed.code);
      return;
    }

    if ('line' in parsed) {
      callbacks.onLine(parsed.line);
    }
  });

  es.addEventListener('error', (event: Event) => {
    if (es.readyState === EventSource.CLOSED) {
      // Server closed — treat as done if we haven't received a done event
      if (open) {
        open = false;
        callbacks.onDone(-1);
      }
      return;
    }
    callbacks.onError(event);
  });

  return {
    close: () => {
      open = false;
      es.close();
    },
    isOpen: () => open,
  };
}

// ── Line classifier — maps raw output text to display category ────────────────

export type LineCategory =
  | 'header'
  | 'section'
  | 'subsection'
  | 'ok'
  | 'warn'
  | 'critical'
  | 'saved'
  | 'separator'
  | 'dim'
  | 'default';

const CLASSIFIERS: Array<{ test: RegExp; category: LineCategory }> = [
  { test: /█/,                            category: 'header'     },
  { test: /^▶▶▶/,                         category: 'section'    },
  { test: /^={3,}/,                       category: 'separator'  },
  { test: /^\s*═{3,}\s+\d/,              category: 'subsection' },
  { test: /✅|\[OK\]/,                    category: 'ok'         },
  { test: /🔴|\[CRIT\]|❌/,              category: 'critical'   },
  { test: /⚠|\[WARN\]/,                  category: 'warn'       },
  { test: /→ Saved:/,                    category: 'saved'      },
  { test: /^\s*$/,                        category: 'dim'        },
];

export function classifyLine(line: string): LineCategory {
  for (const { test, category } of CLASSIFIERS) {
    if (test.test(line)) return category;
  }
  return 'default';
}

// ── Format helpers for terminal display ───────────────────────────────────────

/** Returns a CSS color token string for a given line category */
export function categoryColor(cat: LineCategory): string {
  const map: Record<LineCategory, string> = {
    header:     'var(--blue)',
    section:    'var(--purple)',
    subsection: 'var(--purple)',
    ok:         'var(--success)',
    warn:       'var(--warning)',
    critical:   'var(--danger)',
    saved:      '#60A5FA',
    separator:  'var(--border)',
    dim:        'var(--text-disabled)',
    default:    'var(--text-2)',
  };
  return map[cat];
}
