/**
 * InsightCard — Structured list of AI-generated findings
 *
 * Renders a titled card containing a list of insight bullets.
 * Each insight has a severity level that tints the left border and dot.
 *
 * Usage:
 *   <InsightCard insights={[
 *     { text: 'UNDER bets outperform OVER by 14.8pp', severity: 'positive' },
 *     { text: 'park_factor is constant at 0.990 for all games', severity: 'critical' },
 *   ]} />
 */

import styles from './InsightCard.module.css';

export type InsightSeverity = 'critical' | 'high' | 'medium' | 'positive' | 'info';

export interface Insight {
  text:      string;
  severity?: InsightSeverity;
}

export interface InsightCardProps {
  insights:  Insight[];
  title?:    string;
  icon?:     string;
}

export function InsightCard({
  insights,
  title = 'Key Insights',
  icon  = '💡',
}: InsightCardProps) {
  if (!insights.length) return null;

  return (
    <div className={styles.card} role="region" aria-label={title}>
      <div className={styles.header}>
        <span className={styles.headerIcon} aria-hidden>{icon}</span>
        <span className={styles.headerLabel}>{title}</span>
      </div>

      <ul className={styles.list} role="list">
        {insights.map((ins, i) => {
          const sev = ins.severity ?? 'info';
          return (
            <li
              key={i}
              className={styles.item}
              data-sev={sev}
              role="listitem"
            >
              <span
                className={styles.dot}
                data-sev={sev}
                aria-label={sev}
              />
              {/* Allow basic bold via **text** markdown-lite */}
              <span
                className={styles.itemText}
                dangerouslySetInnerHTML={{
                  __html: ins.text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>'),
                }}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}
