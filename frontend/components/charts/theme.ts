/**
 * Chart colors and text styles from the brand kit's corporate tokens, so Recharts matches the
 * rest of the app. Copper is the main series; other series use the kit's neutral and status inks.
 */

import { corporate } from "@suseelkrishna/fieryfusion-tokens/tokens";

export const COLORS = {
  main: corporate.copper,
  second: corporate.burgundy,
  third: corporate.muted,
  info: corporate.info,
  success: corporate.success,
  warning: corporate.warning,
  grid: corporate.line,
  ink: corporate.ink,
  muted: corporate.muted,
  surface: corporate.surface,
};

/** Series colors in order, for charts with one bar per category such as source. */
export const SERIES = [COLORS.main, COLORS.second, COLORS.info, COLORS.success, COLORS.warning, COLORS.third];

export const AXIS = { stroke: COLORS.grid, tick: { fill: COLORS.muted, fontSize: 12 } };

export const TOOLTIP = {
  contentStyle: {
    background: COLORS.surface,
    border: `1px solid ${COLORS.grid}`,
    borderRadius: 12,
    color: COLORS.ink,
    fontSize: 13,
  },
  cursor: { fill: corporate.subtle },
};

/** Recharts animations are off so the only motion in the app is the page fade. */
export const STILL = { isAnimationActive: false } as const;
