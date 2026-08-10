/**
 * ComingSoonPage — catch-all for sections not yet built
 *
 * Used by the router's wildcard route.
 * Shows the section's icon + name pulled from NAV_SECTIONS.
 */

import { useParams }       from 'react-router-dom';
import { NAV_SECTIONS }    from '@types-athena';
import styles              from './ComingSoonPage.module.css';

export default function ComingSoonPage() {
  const { comingSoon } = useParams<{ comingSoon: string }>();
  const section = NAV_SECTIONS.find(s => s.id === comingSoon);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.icon} aria-hidden>
          {section?.icon ?? '🔬'}
        </div>
        <h1 className={styles.title}>
          {section?.label ?? 'Coming Soon'}
        </h1>
        <p className={styles.sub}>
          This module is under construction. Athena is learning.
        </p>
        <div className={styles.badge}>PLANNED</div>
      </div>
    </div>
  );
}
