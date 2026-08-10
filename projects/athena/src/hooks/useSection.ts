/**
 * useSection — Section navigation hook
 *
 * Clean abstraction over uiStore navigation.
 * Components call navigate() without importing the store directly.
 * Also registers/unregisters voice commands for the active section.
 *
 * Usage:
 *   const { activeSection, navigate, isActive } = useSection();
 */

import { useCallback } from 'react';
import { useUiStore, selectActiveSection } from '@store/uiStore';
import type { SectionId } from '@types-athena';

export function useSection() {
  const activeSection = useUiStore(selectActiveSection);
  const _navigate     = useUiStore(s => s.navigate);
  const openAthena    = useUiStore(s => s.openAthenaPanel);

  const navigate = useCallback(
    (section: SectionId) => {
      _navigate(section);
      // Scroll main content to top on section change
      requestAnimationFrame(() => {
        document.getElementById('athena-main')?.scrollTo({ top: 0, behavior: 'instant' });
      });
    },
    [_navigate]
  );

  const isActive = useCallback(
    (section: SectionId) => activeSection === section,
    [activeSection]
  );

  const askAthena = useCallback(
    (query: string) => openAthena(query),
    [openAthena]
  );

  return { activeSection, navigate, isActive, askAthena };
}

/**
 * useVoiceNavigation — registers "open X" voice commands for the sidebar.
 * Called once at the App level, not per-section.
 */
export function useVoiceNavigation() {
  const navigate         = useUiStore(s => s.navigate);
  const registerCommand  = useUiStore(s => s.registerVoiceCommand);

  // Registers all section navigation commands in one shot.
  // Called from App on mount — no cleanup needed (app-level = always mounted).
  const registerAll = useCallback(() => {
    const sectionMap: Array<{ pattern: RegExp; target: SectionId }> = [
      { pattern: /open (mission control|overview)/i,    target: 'overview'      },
      { pattern: /open (data health|health)/i,          target: 'data-health'   },
      { pattern: /open calibration/i,                   target: 'calibration'   },
      { pattern: /open (over.{0,6}under|ou)/i,          target: 'over-under'    },
      { pattern: /open (features?|feature store)/i,     target: 'features'      },
      { pattern: /open edge/i,                          target: 'edge'          },
      { pattern: /open clv/i,                           target: 'clv'           },
      { pattern: /open teams?/i,                        target: 'teams'         },
      { pattern: /open (filters?|bet optimizer)/i,      target: 'filters'       },
      { pattern: /open temporal/i,                      target: 'temporal'      },
      { pattern: /open root cause/i,                    target: 'root-cause'    },
      { pattern: /open roadmap/i,                       target: 'roadmap'       },
      { pattern: /open (prediction db|database)/i,      target: 'prediction-db' },
    ];

    sectionMap.forEach(({ pattern, target }) => {
      registerCommand({
        pattern,
        label:  `Navigate to ${target}`,
        action: () => navigate(target),
      });
    });
  }, [navigate, registerCommand]);

  return { registerAll };
}
