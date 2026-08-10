/**
 * uiStore — Navigation, layout, and UI interaction state
 *
 * Separated from athenaStore intentionally:
 * UI state changes frequently (hover, nav, voice) and should never
 * trigger re-renders in data-heavy components.
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type { SectionId } from '@types-athena';

// ── Voice command registry ────────────────────────────────────────────────────

interface VoiceCommand {
  pattern:  RegExp;
  action:   () => void;
  label:    string;
}

// ── Notification system ───────────────────────────────────────────────────────

export type NotifLevel = 'info' | 'success' | 'warning' | 'error';

export interface Notification {
  id:      string;
  level:   NotifLevel;
  title:   string;
  message: string;
  ttl:     number;   // ms before auto-dismiss
}

// ── Store shape ───────────────────────────────────────────────────────────────

interface UiStore {
  // Navigation
  activeSection:    SectionId;
  previousSection:  SectionId | null;

  // Layout
  sidebarCollapsed: boolean;

  // Athena AI panel (slides in from right)
  athenaPanelOpen:  boolean;
  athenaPanelQuery: string;   // pre-filled question from "Ask Athena" buttons

  // Voice
  voiceActive:      boolean;
  voiceTranscript:  string;
  voiceCommands:    VoiceCommand[];  // registered by active page

  // Notifications
  notifications:    Notification[];

  // Run stream (diagnostics)
  streamRunning:    boolean;
  streamOutput:     string[];
  streamDone:       boolean;

  // Actions — Navigation
  navigate:         (section: SectionId) => void;

  // Actions — Layout
  toggleSidebar:    () => void;
  setSidebarCollapsed: (v: boolean) => void;

  // Actions — Athena panel
  openAthenaPanel:  (query?: string) => void;
  closeAthenaPanel: () => void;

  // Actions — Voice
  setVoiceActive:   (v: boolean) => void;
  setVoiceTranscript: (t: string) => void;
  registerVoiceCommand:   (cmd: VoiceCommand) => void;
  unregisterVoiceCommand: (pattern: string) => void;

  // Actions — Notifications
  notify:           (n: Omit<Notification, 'id'>) => void;
  dismissNotif:     (id: string) => void;
  clearNotifs:      () => void;

  // Actions — Stream
  startStream:      () => void;
  appendStreamLine: (line: string) => void;
  endStream:        () => void;
  clearStream:      () => void;
}

// ── Store ─────────────────────────────────────────────────────────────────────

export const useUiStore = create<UiStore>()(
  devtools(
    persist(
      (set, get) => ({
        // Defaults
        activeSection:    'overview',
        previousSection:  null,
        sidebarCollapsed: false,
        athenaPanelOpen:  false,
        athenaPanelQuery: '',
        voiceActive:      false,
        voiceTranscript:  '',
        voiceCommands:    [],
        notifications:    [],
        streamRunning:    false,
        streamOutput:     [],
        streamDone:       false,

        // Navigation
        navigate: (section) =>
          set(
            s => ({ activeSection: section, previousSection: s.activeSection }),
            false,
            `navigate/${section}`
          ),

        // Layout
        toggleSidebar: () =>
          set(s => ({ sidebarCollapsed: !s.sidebarCollapsed }), false, 'toggleSidebar'),

        setSidebarCollapsed: (v) =>
          set({ sidebarCollapsed: v }, false, 'setSidebarCollapsed'),

        // Athena panel
        openAthenaPanel: (query = '') =>
          set({ athenaPanelOpen: true, athenaPanelQuery: query }, false, 'openAthenaPanel'),

        closeAthenaPanel: () =>
          set({ athenaPanelOpen: false, athenaPanelQuery: '' }, false, 'closeAthenaPanel'),

        // Voice
        setVoiceActive: (v) =>
          set({ voiceActive: v }, false, 'setVoiceActive'),

        setVoiceTranscript: (t) =>
          set({ voiceTranscript: t }, false, 'setVoiceTranscript'),

        registerVoiceCommand: (cmd) =>
          set(
            s => ({ voiceCommands: [...s.voiceCommands, cmd] }),
            false,
            'registerVoiceCommand'
          ),

        unregisterVoiceCommand: (pattern) =>
          set(
            s => ({
              voiceCommands: s.voiceCommands.filter(
                c => c.pattern.toString() !== pattern
              ),
            }),
            false,
            'unregisterVoiceCommand'
          ),

        // Notifications
        notify: (n) => {
          const id = `notif_${Date.now()}_${Math.random().toString(36).slice(2)}`;
          const notif: Notification = { ...n, id };
          set(
            s => ({ notifications: [notif, ...s.notifications].slice(0, 6) }),
            false,
            'notify'
          );
          if (n.ttl > 0) {
            setTimeout(() => get().dismissNotif(id), n.ttl);
          }
        },

        dismissNotif: (id) =>
          set(
            s => ({ notifications: s.notifications.filter(n => n.id !== id) }),
            false,
            'dismissNotif'
          ),

        clearNotifs: () => set({ notifications: [] }, false, 'clearNotifs'),

        // Stream
        startStream: () =>
          set({ streamRunning: true, streamOutput: [], streamDone: false }, false, 'startStream'),

        appendStreamLine: (line) =>
          set(
            s => ({ streamOutput: [...s.streamOutput, line] }),
            false,
            'appendStreamLine'
          ),

        endStream: () =>
          set({ streamRunning: false, streamDone: true }, false, 'endStream'),

        clearStream: () =>
          set({ streamOutput: [], streamDone: false }, false, 'clearStream'),
      }),
      {
        name: 'athena-ui',
        // Only persist layout preferences — never persist stream output or voice
        partialize: (s) => ({
          sidebarCollapsed: s.sidebarCollapsed,
          activeSection:    s.activeSection,
        }),
      }
    ),
    { name: 'UiStore' }
  )
);

// ── Selectors ─────────────────────────────────────────────────────────────────

export const selectActiveSection    = (s: UiStore) => s.activeSection;
export const selectSidebarCollapsed = (s: UiStore) => s.sidebarCollapsed;
export const selectAthenaPanelOpen  = (s: UiStore) => s.athenaPanelOpen;
export const selectAthenaPanelQuery = (s: UiStore) => s.athenaPanelQuery;
export const selectVoiceActive      = (s: UiStore) => s.voiceActive;
export const selectVoiceTranscript  = (s: UiStore) => s.voiceTranscript;
export const selectNotifications    = (s: UiStore) => s.notifications;
export const selectStreamRunning    = (s: UiStore) => s.streamRunning;
export const selectStreamOutput     = (s: UiStore) => s.streamOutput;
export const selectStreamDone       = (s: UiStore) => s.streamDone;
