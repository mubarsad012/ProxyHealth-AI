// "Big Calm" design tokens (DECISIONS D-28, PRODUCT_SPEC §5.1, ARCHITECTURE §3.1).
// Pure data: no React, no platform imports. `design/theme.tsx` (WP4) composes these with
// the colour scheme, the high-contrast toggle and AccessibilityInfo flags.
//
// Contrast floors (checked with the WCAG 2.x formula when this file was written):
//   body text ≥ 7:1 on `background` and `surface` in every palette (never below 4.5:1),
//   UI components (borders, icons, urgency words) ≥ 3:1; urgency words ≥ 4.5:1.

import type { UrgencyLevel } from '@/api/types';

/** Type scale. Base 18, body never below 16. `allowFontScaling` stays on everywhere;
 *  `maxFontSizeMultiplier` 2.0 is applied only to tab labels (D-28). */
export const type = {
  family: 'NotoSans',
  size: {
    caption: 16,
    body: 18,
    bodyLarge: 20,
    title: 24,
    heading: 28,
    display: 34,
  },
  lineHeight: {
    caption: 22,
    body: 26,
    bodyLarge: 28,
    title: 32,
    heading: 36,
    display: 42,
  },
  weight: {
    regular: '400',
    bold: '700',
  },
  minBody: 16,
  /** Only for tab labels; body text is never capped. */
  tabLabelMaxFontSizeMultiplier: 2,
} as const;

/** Control sizes in pt. Every screen has exactly one 72 pt primary action. */
export const size = {
  button: 56,
  primaryCta: 72,
  speakButton: 44,
  tabBar: 64,
  minTouch: 44,
  hitSlop: 8,
  icon: 24,
  iconLarge: 32,
} as const;

/** Spacing scale in pt (8 pt touch spacing between controls). */
export const space = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
  touchGap: 8,
  screenGutter: 16,
} as const;

export const radius = {
  sm: 6,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

export interface Palette {
  background: string;
  surface: string;
  surfaceRaised: string;
  text: string;
  textMuted: string;
  primary: string;
  onPrimary: string;
  secondary: string;
  onSecondary: string;
  border: string;
  divider: string;
  danger: string;
  onDanger: string;
  success: string;
  warning: string;
  link: string;
  focus: string;
  overlay: string;
}

const light: Palette = {
  background: '#FFFFFF',
  surface: '#F4F6F8',
  surfaceRaised: '#FFFFFF',
  text: '#14202B', // 16.5:1 on background
  textMuted: '#3E4C5A', // 8.8:1 on background
  primary: '#0B4F8A', // 8.4:1 on background; white on it 8.4:1
  onPrimary: '#FFFFFF',
  secondary: '#E3ECF5',
  onSecondary: '#0B4F8A',
  border: '#7A8794', // 3.7:1 on background (UI component floor 3:1)
  divider: '#D5DCE3',
  danger: '#A61B1B', // 7.5:1 on background
  onDanger: '#FFFFFF',
  success: '#175E33', // 7.4:1 on background
  warning: '#8A5200', // 6.6:1 on background (word + icon, never colour alone)
  link: '#0B4F8A',
  focus: '#0B4F8A',
  overlay: 'rgba(20, 32, 43, 0.55)',
};

const dark: Palette = {
  background: '#0F1720',
  surface: '#1A2431',
  surfaceRaised: '#22303F',
  text: '#F3F6F9', // 16.6:1 on background
  textMuted: '#C3CDD7', // 11.2:1 on background
  primary: '#9CC4F5', // 10:1 on background
  onPrimary: '#0F1720',
  secondary: '#22303F',
  onSecondary: '#9CC4F5',
  border: '#8A98A6', // 6.1:1 on background
  divider: '#33414F',
  danger: '#F5A3A3', // 9.2:1 on background
  onDanger: '#0F1720',
  success: '#8FD3A8',
  warning: '#FCD34D',
  link: '#9CC4F5',
  focus: '#9CC4F5',
  overlay: 'rgba(0, 0, 0, 0.7)',
};

const highContrast: Palette = {
  background: '#FFFFFF',
  surface: '#FFFFFF',
  surfaceRaised: '#FFFFFF',
  text: '#000000', // 21:1
  textMuted: '#000000',
  primary: '#00297A', // 13.1:1
  onPrimary: '#FFFFFF',
  secondary: '#FFFFFF',
  onSecondary: '#00297A',
  border: '#000000',
  divider: '#000000',
  danger: '#8A0000', // 10.1:1
  onDanger: '#FFFFFF',
  success: '#004D1A', // 10.1:1
  warning: '#5C3A00',
  link: '#00297A',
  focus: '#000000',
  overlay: 'rgba(0, 0, 0, 0.8)',
};

export const palette = { light, dark, highContrast } as const;
export type PaletteName = keyof typeof palette;

/** Urgency is always icon + word + colour, never colour alone, never CAPS (PRODUCT_SPEC §5.5).
 *  `icon` names are vector glyph ids rendered with an `accessibilityLabel`; `wordKey` is a pack key. */
export interface UrgencyToken {
  icon: 'alert' | 'calendar-alert' | 'calendar-clock' | 'calendar' | 'info';
  wordKey: `urgency.word.${UrgencyLevel}`;
  /** Foreground colour of icon + word per palette (≥ 4.5:1 on that palette's background). */
  color: Record<PaletteName, string>;
}

export const urgency: Record<UrgencyLevel, UrgencyToken> = {
  emergency: {
    icon: 'alert',
    wordKey: 'urgency.word.emergency',
    color: { light: '#7F1D1D', dark: '#FCA5A5', highContrast: '#7F1D1D' }, // red-900 on white
  },
  critical: {
    icon: 'calendar-alert',
    wordKey: 'urgency.word.critical',
    color: { light: '#A61B1B', dark: '#FCA5A5', highContrast: '#8A0000' }, // red-700
  },
  high: {
    icon: 'calendar-clock',
    wordKey: 'urgency.word.high',
    color: { light: '#A33A06', dark: '#FDBA74', highContrast: '#7A2A00' }, // orange-700
  },
  medium: {
    icon: 'calendar',
    wordKey: 'urgency.word.medium',
    color: { light: '#8A5200', dark: '#FCD34D', highContrast: '#5C3A00' }, // amber-700 / amber-300
  },
  info: {
    icon: 'info',
    wordKey: 'urgency.word.info',
    color: { light: '#1A4FC4', dark: '#93C5FD', highContrast: '#00297A' }, // blue-700
  },
};

/** The nine bundled Noto families (PRODUCT_SPEC §5.1 Fonts row). Keys equal `font_hint` values in
 *  `data/languages.yaml`; `null` font_hint (CJK) falls back to the system font. Files live in
 *  `assets/fonts/` (byte copies of `apps/api/data/fonts/` kept equal by sync_to_mobile.py); the
 *  expo-font `require` map is built in `i18n/fonts.ts` (WP4) from `file.regular` / `file.bold`. */
export interface FontFamilyToken {
  regular: string;
  bold: string;
  file: { regular: string; bold: string };
  /** Multiply the type-scale line height by this. Nastaliq needs 2.0 (PRODUCT_SPEC §5.1). */
  lineHeightFactor: number;
}

function noto(name: string, lineHeightFactor = 1): FontFamilyToken {
  return {
    regular: `${name}-Regular`,
    bold: `${name}-Bold`,
    file: { regular: `${name}-Regular.ttf`, bold: `${name}-Bold.ttf` },
    lineHeightFactor,
  };
}

export const fonts = {
  NotoSans: noto('NotoSans'),
  NotoNaskhArabic: noto('NotoNaskhArabic', 1.25),
  NotoNastaliqUrdu: noto('NotoNastaliqUrdu', 2.0),
  NotoSansEthiopic: noto('NotoSansEthiopic'),
  NotoSansMyanmar: noto('NotoSansMyanmar', 1.35),
  NotoSansDevanagari: noto('NotoSansDevanagari', 1.2),
  NotoSansBengali: noto('NotoSansBengali', 1.2),
  NotoSansGurmukhi: noto('NotoSansGurmukhi', 1.2),
  NotoSansHanifiRohingya: noto('NotoSansHanifiRohingya', 1.3),
} as const satisfies Record<string, FontFamilyToken>;

export type FontHint = keyof typeof fonts;

/** Resolve a pack `font_hint` to a family token; unknown or null hints use the system font. */
export function fontForHint(hint: string | null | undefined): FontFamilyToken | null {
  if (!hint) return null;
  return Object.prototype.hasOwnProperty.call(fonts, hint) ? fonts[hint as FontHint] : null;
}

export const motion = {
  /** Durations in ms; theme.tsx zeroes them when reduce-motion is on. */
  fast: 120,
  normal: 200,
  slow: 320,
} as const;

export const a11y = {
  bodyContrastMin: 7,
  bodyContrastFloor: 4.5,
  uiContrastMin: 3,
  wcagLevel: 'AA' as const,
  wcagVersion: '2.2' as const,
} as const;

export const tokens = { type, size, space, radius, palette, urgency, fonts, motion, a11y } as const;
export default tokens;
