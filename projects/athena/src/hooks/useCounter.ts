/**
 * useCounter — Animated number counter
 *
 * Counts from 0 (or previous value) to `target` over `duration` ms.
 * Uses requestAnimationFrame — GPU-timed, no setInterval drift.
 *
 * Usage:
 *   const displayed = useCounter(48.3, { decimals: 1, duration: 800 });
 *   // renders: 0.0 → 48.3 on mount, smooth
 */

import { useEffect, useRef, useState } from 'react';

interface CounterOptions {
  /** Decimal places to display (default: 0) */
  decimals?: number;
  /** Animation duration in ms (default: 900) */
  duration?: number;
  /** Easing function — default ease-out-cubic */
  easing?: (t: number) => number;
  /** Start from this value instead of 0 (default: 0) */
  from?: number;
}

const easeOutCubic = (t: number): number => 1 - Math.pow(1 - t, 3);

export function useCounter(
  target: number,
  {
    decimals = 0,
    duration = 900,
    easing   = easeOutCubic,
    from     = 0,
  }: CounterOptions = {}
): string {
  const [current, setCurrent] = useState(from);
  const rafRef    = useRef<number>(0);
  const startRef  = useRef<number | null>(null);
  const fromRef   = useRef(from);

  useEffect(() => {
    // Cancel any in-flight animation
    cancelAnimationFrame(rafRef.current);

    const startValue = fromRef.current;
    const delta      = target - startValue;

    if (delta === 0) return;

    const animate = (timestamp: number) => {
      if (startRef.current === null) startRef.current = timestamp;
      const elapsed  = timestamp - startRef.current;
      const progress = Math.min(elapsed / duration, 1);
      const value    = startValue + delta * easing(progress);

      setCurrent(value);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      } else {
        setCurrent(target);
        fromRef.current  = target;
        startRef.current = null;
      }
    };

    startRef.current = null;
    rafRef.current   = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, easing]);

  return current.toFixed(decimals);
}

/**
 * useCounterValue — Same as useCounter but returns a raw number
 * (useful when you want to format the number yourself)
 */
export function useCounterValue(target: number, duration = 900): number {
  const [current, setCurrent] = useState(0);
  const rafRef   = useRef<number>(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    cancelAnimationFrame(rafRef.current);
    const start = 0;
    const delta = target - start;

    const animate = (ts: number) => {
      if (startRef.current === null) startRef.current = ts;
      const p = Math.min((ts - startRef.current) / duration, 1);
      setCurrent(start + delta * easeOutCubic(p));
      if (p < 1) rafRef.current = requestAnimationFrame(animate);
      else { setCurrent(target); startRef.current = null; }
    };

    startRef.current = null;
    rafRef.current   = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration]);

  return current;
}
