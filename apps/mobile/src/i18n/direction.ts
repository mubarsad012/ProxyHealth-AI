// Direction (D-26, PRODUCT_SPEC §5.2). `useDirection()` derives everything from the active pack so
// RTL is correct immediately in Expo Go, dev builds and web without a restart:
//
// * Layout mirroring is done by OUR `row` value. On web the RNW root is pinned to `direction: ltr`
//   (global.css) so `row-reverse` flips reliably; `document.documentElement.dir`/`lang` are still
//   set from the pack for the browser, assistive tech and the `:root[dir=rtl]` CSS helpers.
// * On native, once the app has restarted with `I18nManager.isRTL` matching the pack, React
//   Native mirrors `row` and swaps `textAlign` left/right itself, so neither may be flipped again
//   (that would double-flip).
// * Switching to/from RTL on native calls `allowRTL/forceRTL` (applies on next start) and sets
//   `restartPending`; the UI shows `direction.restart_prompt`. `expo-updates` is not installed.

import { I18nManager, Platform } from 'react-native';

import type { Direction } from '@/api/types';
import { useI18n } from '@/i18n/store';
import { webDocument } from '@/lib/platform';

export interface DirectionInfo {
  isRTL: boolean;
  row: 'row' | 'row-reverse';
  textAlign: 'left' | 'right';
  writingDirection: 'ltr' | 'rtl';
  dir: 'ltr' | 'rtl';
  /** `alignSelf`/`alignItems` value for "start of the line" (flex-start in LTR, mirrored in RTL). */
  alignStart: 'flex-start' | 'flex-end';
  /** The opposite end of the line. */
  alignEnd: 'flex-start' | 'flex-end';
}

/** True when the native layout engine already mirrors rows (I18nManager RTL after a restart). */
export function nativeLayoutIsRTL(): boolean {
  if (Platform.OS === 'web') return false;
  try {
    return Boolean(I18nManager.isRTL);
  } catch {
    return false;
  }
}

/** Pure derivation, exported for tests and non-hook code. */
export function directionInfo(direction: Direction, nativeRTL: boolean = nativeLayoutIsRTL()): DirectionInfo {
  const isRTL = direction === 'rtl';
  const flipped = isRTL !== nativeRTL;
  return {
    isRTL,
    row: flipped ? 'row-reverse' : 'row',
    // React Native swaps left/right itself when the layout is RTL (iOS RCTAttributedTextUtils,
    // Android TextLayoutManager ALIGN_OPPOSITE), so alignment follows `flipped` like `row` does.
    textAlign: flipped ? 'right' : 'left',
    writingDirection: isRTL ? 'rtl' : 'ltr',
    dir: isRTL ? 'rtl' : 'ltr',
    alignStart: flipped ? 'flex-end' : 'flex-start',
    alignEnd: flipped ? 'flex-start' : 'flex-end',
  };
}

export function useDirection(): DirectionInfo {
  const direction = useI18n((s) => s.pack.direction);
  return directionInfo(direction);
}

/** Native only: does the pack direction differ from the layout the app was started with? */
export function useRestartPending(): boolean {
  return useI18n((s) => s.restartPending);
}

/**
 * The RTL value last passed to `forceRTL` this session (null = none yet). `I18nManager.isRTL` is a
 * start-up constant, so it cannot tell us what will apply on the NEXT start once we have forced
 * something; this does. Without it, a transient LTR call (e.g. English before the saved Arabic
 * pack is applied) would persist LTR and a later RTL call would never re-force RTL.
 */
let lastForcedRTL: boolean | null = null;

/** Test hook: forget what was forced this session. */
export function resetDirectionForTests(): void {
  lastForcedRTL = null;
}

/**
 * Side effects of a direction/tag change. Web: sets `<html dir lang>`. Native: syncs
 * `I18nManager` for the next start (whenever the value that would apply next start differs) and
 * flags the restart prompt when the running layout differs from the pack. Returns true when a
 * native restart is now pending. Safe to call repeatedly and in Node (static export).
 */
export function applyDirection(direction: Direction, tag: string): boolean {
  const isRTL = direction === 'rtl';
  if (Platform.OS === 'web') {
    const doc = webDocument();
    if (doc?.documentElement) {
      doc.documentElement.setAttribute('dir', isRTL ? 'rtl' : 'ltr');
      doc.documentElement.setAttribute('lang', tag);
    }
    useI18n.getState().setRestartPending(false);
    return false;
  }
  let pending = false;
  try {
    const startedRTL = Boolean(I18nManager.isRTL);
    const nextStartRTL = lastForcedRTL ?? startedRTL;
    if (nextStartRTL !== isRTL) {
      I18nManager.allowRTL(isRTL);
      I18nManager.forceRTL(isRTL);
      lastForcedRTL = isRTL;
    }
    pending = startedRTL !== isRTL;
  } catch {
    pending = false;
  }
  useI18n.getState().setRestartPending(pending);
  return pending;
}
