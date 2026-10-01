// ThemeProvider + hooks (D-28, ARCHITECTURE §3.1). Composes the colour scheme, the user's
// high-contrast toggle OR the OS accessibility flags, reduce-motion and the text-size setting with
// the pure tokens in `tokens.ts`. Nothing here touches the network or storage.

import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { AccessibilityInfo, Platform } from 'react-native';

import { motion, palette, type Palette, type PaletteName, tokens } from '@/design/tokens';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { useSettings } from '@/store/settings';

export type TextSize = 'normal' | 'large' | 'xl';

/** Multiplier applied on top of the OS font scale for the user's in-app text-size choice. */
export const textSizeFactor: Record<TextSize, number> = { normal: 1, large: 1.2, xl: 1.45 };

export interface Theme {
  /** Which palette is active. */
  name: PaletteName;
  scheme: 'light' | 'dark';
  colors: Palette;
  highContrast: boolean;
  reduceMotion: boolean;
  textSize: TextSize;
  /** In-app text factor (OS scaling is applied separately by React Native). */
  textFactor: number;
  /** Motion durations already zeroed when reduce-motion is on. */
  motion: { fast: number; normal: number; slow: number };
  tokens: typeof tokens;
}

const defaultTheme: Theme = {
  name: 'light',
  scheme: 'light',
  colors: palette.light,
  highContrast: false,
  reduceMotion: false,
  textSize: 'normal',
  textFactor: 1,
  motion,
  tokens,
};

const ThemeContext = createContext<Theme>(defaultTheme);

type A11yFlagFn = (() => Promise<boolean>) | undefined;

/** Reads an optional AccessibilityInfo flag; missing on some platforms (web has none of them). */
async function readFlag(fn: A11yFlagFn): Promise<boolean> {
  if (typeof fn !== 'function') return false;
  try {
    return Boolean(await fn());
  } catch {
    return false;
  }
}

/** OS-level "increase contrast" signals: Android `isHighTextContrastEnabled`, iOS
 *  `isDarkerSystemColorsEnabled`. Web has no API for this, so the toggle alone applies. */
export function useSystemHighContrast(): boolean {
  const [on, setOn] = useState(false);
  useEffect(() => {
    if (Platform.OS === 'web') return;
    let cancelled = false;
    const info = AccessibilityInfo as unknown as Record<string, A11yFlagFn>;
    Promise.all([
      readFlag(info.isHighTextContrastEnabled),
      readFlag(info.isDarkerSystemColorsEnabled),
    ]).then(([a, b]) => {
      if (!cancelled) setOn(a || b);
    });
    const subs = [
      safeAddListener('highTextContrastChanged', (v) => setOn(Boolean(v))),
      safeAddListener('darkerSystemColorsChanged', (v) => setOn(Boolean(v))),
    ];
    return () => {
      cancelled = true;
      subs.forEach((s) => s?.remove());
    };
  }, []);
  return on;
}

function safeAddListener(
  event: string,
  handler: (value: boolean) => void,
): { remove(): void } | null {
  try {
    const add = (
      AccessibilityInfo as unknown as {
        addEventListener?: (e: string, h: (v: boolean) => void) => { remove(): void };
      }
    ).addEventListener;
    return typeof add === 'function' ? add(event, handler) : null;
  } catch {
    return null;
  }
}

/** Reduce-motion preference (OS). Web: `prefers-reduced-motion`. */
function webReduceMotionQuery(): MediaQueryList | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined' || typeof window.matchMedia !== 'function') return null;
  return window.matchMedia('(prefers-reduced-motion: reduce)');
}

export function useSystemReduceMotion(): boolean {
  const [on, setOn] = useState(() => webReduceMotionQuery()?.matches ?? false);
  useEffect(() => {
    if (Platform.OS === 'web') {
      const mq = webReduceMotionQuery();
      if (!mq) return;
      const listener = (e: MediaQueryListEvent) => setOn(e.matches);
      mq.addEventListener?.('change', listener);
      return () => mq.removeEventListener?.('change', listener);
    }
    let cancelled = false;
    readFlag(AccessibilityInfo.isReduceMotionEnabled).then((v) => {
      if (!cancelled) setOn(v);
    });
    const sub = safeAddListener('reduceMotionChanged', (v) => setOn(Boolean(v)));
    return () => {
      cancelled = true;
      sub?.remove();
    };
  }, []);
  return on;
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const schemeRaw = useColorScheme();
  const scheme: 'light' | 'dark' = schemeRaw === 'dark' ? 'dark' : 'light';
  const userHighContrast = useSettings((s) => s.highContrast);
  const textSize = useSettings((s) => s.textSize);
  const systemHighContrast = useSystemHighContrast();
  const reduceMotion = useSystemReduceMotion();
  const highContrast = userHighContrast || systemHighContrast;

  const value = useMemo<Theme>(() => {
    const name: PaletteName = highContrast ? 'highContrast' : scheme;
    return {
      name,
      scheme,
      colors: palette[name],
      highContrast,
      reduceMotion,
      textSize,
      textFactor: textSizeFactor[textSize],
      motion: reduceMotion ? { fast: 0, normal: 0, slow: 0 } : motion,
      tokens,
    };
  }, [scheme, highContrast, reduceMotion, textSize]);

  const focus = value.colors.focus;
  useEffect(() => {
    applyWebFocusColor(focus);
  }, [focus]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

/** Web: the `:focus-visible` ring in global.css reads `--ph-focus`; keep it on the palette in use
 *  (the fixed light-palette blue was ~2:1 on the dark backgrounds). No-op on native. */
export function applyWebFocusColor(color: string, doc: { documentElement?: { style?: { setProperty?(k: string, v: string): void } } } | undefined = webDocument()): void {
  try {
    doc?.documentElement?.style?.setProperty?.('--ph-focus', color);
  } catch {
    // no DOM (static export / tests)
  }
}

function webDocument(): Document | undefined {
  if (Platform.OS !== 'web' || typeof document === 'undefined') return undefined;
  return document;
}

export function useTheme(): Theme {
  return useContext(ThemeContext);
}

/** User toggle OR OS accessibility flags (D-28). */
export function useHighContrast(): boolean {
  return useContext(ThemeContext).highContrast;
}

export function useReduceMotion(): boolean {
  return useContext(ThemeContext).reduceMotion;
}

/** Scaled font size for the in-app text-size setting (OS scaling still applies on top). */
export function useScaled(): (size: number) => number {
  const { textFactor } = useContext(ThemeContext);
  return (size: number) => Math.round(size * textFactor);
}
