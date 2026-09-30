// Bidi helpers (D-26, PRODUCT_SPEC §5.2 rule 2). Pure: no React / React Native imports, so `useT`,
// the `Bidi` component and plain-text builders share one definition.
//
// Inside an RTL layout every `AppText` paragraph runs right-to-left, so a string whose strong
// characters are all left-to-right (an English fallback, a pseudo-localized "⟦rhg⟧ Need help
// now?", a Latin sender name) would show its trailing punctuation at the wrong end ("?Need help
// now ⟦rhg⟧", "...language"). Such a string is wrapped in FSI…PDI (first-strong isolate): inside
// the isolate it keeps its own direction, and as a whole it is placed in the RTL paragraph. Mixed
// strings (Dari with an embedded Latin word) keep the layout direction; the Unicode bidi algorithm
// already orders their runs.

export const LRI = '\u2066';
export const RLI = '\u2067';
export const FSI = '\u2068';
export const PDI = '\u2069';

export type BidiDir = 'ltr' | 'rtl' | 'auto';
export type LayoutDir = 'ltr' | 'rtl';
export type StrongDirection = 'ltr' | 'rtl' | 'mixed' | 'neutral';

// Bidi class R/AL: Hebrew … Arabic Extended-A (U+0590–U+08FF), Hebrew and Arabic presentation
// forms, and Hanifi Rohingya (U+10D00–U+10D3F, UTF-16 D803 DD00–DD3F). No `\p{…}` classes and no
// `u` flag: the ranges stay portable across Hermes and JSC.
const RTL_RE = /[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefe]|\ud803[\udd00-\udd3f]/;
// Bidi class L (approximation): Latin, Greek, Cyrillic, Armenian, Indic and Southeast Asian
// scripts, Myanmar, Georgian, Hangul, Ethiopic, Cherokee, Khmer, Latin Extended Additional and
// Greek Extended, kana, CJK, Yi, full-width Latin.
const LTR_RE =
  /[A-Za-z\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u02b8\u0370-\u03ff\u0400-\u052f\u0531-\u058f\u0900-\u0dff\u0e00-\u0fff\u1000-\u10ff\u1100-\u11ff\u1200-\u13ff\u1780-\u17ff\u1e00-\u1fff\u2c00-\u2dff\u3040-\u31ff\u3400-\u4dbf\u4e00-\u9fff\ua000-\ua4cf\uac00-\ud7af\uf900-\ufaff\uff21-\uff3a\uff41-\uff5a]/;
const ISOLATE_RE = /[\u2066-\u2069]/g;

export function isolateChar(dir: BidiDir): string {
  return dir === 'ltr' ? LRI : dir === 'rtl' ? RLI : FSI;
}

/** Wrap a plain string in isolate marks (LRI/RLI/FSI … PDI). */
export function isolate(text: string, dir: BidiDir = 'ltr'): string {
  return `${isolateChar(dir)}${text}${PDI}`;
}

/** Strip isolate marks (clipboard, quick-sheet text, comparisons). */
export function stripIsolates(text: string): string {
  return text.replace(ISOLATE_RE, '');
}

/** Which way the strong characters of `text` run (isolated content included). */
export function strongDirection(text: string): StrongDirection {
  const rtl = RTL_RE.test(text);
  const ltr = LTR_RE.test(text);
  return rtl && ltr ? 'mixed' : rtl ? 'rtl' : ltr ? 'ltr' : 'neutral';
}

/**
 * Direction of the first strong character outside any isolate (Unicode rules P2/P3 — what FSI and
 * `dir="auto"` use); null when there is none (digits, punctuation).
 */
export function firstStrongDirection(text: string): LayoutDir | null {
  let depth = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (ch === LRI || ch === RLI || ch === FSI) {
      depth += 1;
      continue;
    }
    if (ch === PDI) {
      depth = Math.max(0, depth - 1);
      continue;
    }
    if (depth > 0) continue;
    const code = ch.charCodeAt(0);
    const unit = code >= 0xd800 && code <= 0xdbff && i + 1 < text.length ? text.slice(i, i + 2) : ch;
    if (RTL_RE.test(unit)) return 'rtl';
    if (LTR_RE.test(unit)) return 'ltr';
    if (unit.length === 2) i += 1;
  }
  return null;
}

/** True when the whole string is already one isolate (nothing to add). */
function isIsolated(text: string): boolean {
  return (text.startsWith(FSI) || text.startsWith(LRI) || text.startsWith(RLI)) && text.endsWith(PDI);
}

/**
 * For a paragraph laid out in `layout`: a string whose strong characters all run the other way is
 * wrapped in FSI…PDI; mixed, neutral, same-direction and already-isolated strings are returned as
 * they are.
 */
export function isolateForLayout(text: string, layout: LayoutDir): string {
  if (!text || isIsolated(text)) return text;
  const dir = strongDirection(text);
  const foreign = layout === 'rtl' ? dir === 'ltr' : dir === 'rtl';
  return foreign ? isolate(text, 'auto') : text;
}

const PLACEHOLDER_RE = /\{[a-zA-Z0-9_]+\}/g;

/**
 * `isolateForLayout` for copy built from a pack template: the direction is decided on the template
 * with its `{placeholders}` removed, not on the interpolated text. An all-LTR template (an English
 * fallback, a pseudo "⟦rhg⟧ No {language} voice…") stays isolated when an RTL variable (a Dari or
 * Rohingya language name) is inserted — FSI when the result's first strong character runs the
 * template's way, else an explicit LRI (RLI in an LTR layout). A template of the layout's direction
 * or mixed is left alone; a neutral template ("{count}") falls back to the interpolated text.
 */
export function isolateTemplateForLayout(template: string, text: string, layout: LayoutDir): string {
  if (!text || isIsolated(text)) return text;
  const dir = strongDirection(template.replace(PLACEHOLDER_RE, ''));
  if (dir === 'neutral') return isolateForLayout(text, layout);
  const own: LayoutDir = layout === 'rtl' ? 'ltr' : 'rtl';
  if (dir !== own) return text;
  return isolate(text, firstStrongDirection(text) === own ? 'auto' : own);
}

/**
 * The concrete direction for `Bidi dir="auto"`: the first strong character of the text, else the
 * surrounding layout. Resolving it (instead of leaving `auto`) matters on web, where `AppText`'s
 * inline `direction` from the pack would otherwise beat the `dir="auto"` attribute.
 */
export function resolveAuto(text: string, layout: LayoutDir): LayoutDir {
  return firstStrongDirection(text) ?? layout;
}
