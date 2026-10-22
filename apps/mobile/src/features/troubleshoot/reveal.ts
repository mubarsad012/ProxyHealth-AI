// S16: a new result appears below the form, under the fold (the sample button sits low on the
// screen). When one arrives it is brought into view and focus moves to its first heading:
//   web    → the result's DOM node is scrolled into view inside the screen's scroll container and
//            its first heading gets keyboard/screen-reader focus (tabindex -1, no second scroll);
//   native → accessibility focus moves to the result (VoiceOver / TalkBack scroll to what they
//            focus). The shared `Screen` keeps its ScrollView private, so no visual scroll there.

import { AccessibilityInfo, findNodeHandle, Platform } from 'react-native';

const HEADING = '[role="heading"], h1, h2, h3, h4, h5, h6';

interface WebNode {
  scrollIntoView?(opts?: ScrollIntoViewOptions): void;
  querySelector?(selector: string): WebNode | null;
  hasAttribute?(name: string): boolean;
  setAttribute?(name: string, value: string): void;
  focus?(opts?: FocusOptions): void;
}

export function revealOnWeb(node: unknown, opts: { smooth: boolean }): boolean {
  const el = node as WebNode | null;
  if (!el || typeof el.scrollIntoView !== 'function') return false;
  el.scrollIntoView({ behavior: opts.smooth ? 'smooth' : 'auto', block: 'start' });
  const heading = el.querySelector?.(HEADING) ?? null;
  if (heading && typeof heading.focus === 'function') {
    if (!heading.hasAttribute?.('tabindex')) heading.setAttribute?.('tabindex', '-1');
    heading.focus({ preventScroll: true });
  }
  return true;
}

/** Bring a just-arrived result into view and move focus to it (see the file comment). */
export function revealResult(node: unknown, opts: { smooth: boolean }): void {
  if (!node) return;
  try {
    if (Platform.OS === 'web') {
      revealOnWeb(node, opts);
      return;
    }
    const tag = findNodeHandle(node as Parameters<typeof findNodeHandle>[0]);
    if (tag != null) AccessibilityInfo.setAccessibilityFocus(tag);
  } catch {
    // best-effort: the result is on screen either way
  }
}
