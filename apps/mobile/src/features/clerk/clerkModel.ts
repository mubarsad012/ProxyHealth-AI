// Clerk card view-model (D-18, PRODUCT_SPEC §8). The English card is fixed copy: from an analysis
// it is `clerk_message.english` (built server-side from the fixed template) plus appended lines
// rendered from ENGLISH base strings (`clerk.interpreter_hhs` only, and only when the server
// listed it); the generic card uses the fixed template with a preset or the user's own words.
// English lines always come from `BASE_STRINGS` (never the UI pack) — the card is for the clerk.

import type { AnalysisResult } from '@/api/types';
import { LANGUAGES } from '@/i18n/languages';
import { BASE_STRINGS, interpolate } from '@/i18n/store';
import type { TFunction } from '@/i18n/useT';

export const CLERK_HOLD_MS = 1500;
export const CLERK_OWN_WORDS_MAX = 200;

export const CLERK_PRESETS = ['appointment', 'bill', 'form', 'address', 'benefits'] as const;
export type ClerkPreset = (typeof CLERK_PRESETS)[number];

export type ClerkNeed = { kind: 'default' } | { kind: 'preset'; preset: ClerkPreset } | { kind: 'own'; text: string };

/** Only keys the client may append (v1: the HHS interpreter line). */
const APPENDABLE = new Set(['clerk.interpreter_hhs']);

export interface ClerkCard {
  /** English lines shown to the clerk, in order. */
  english: string[];
  /** The same card in the user's language (shown collapsed to the user). */
  translated: string;
  /** True when part of the card is the user's own typed words (shown with "Your words"). */
  ownWords: boolean;
}

function english(key: string, vars?: Record<string, string | number>): string {
  return interpolate(BASE_STRINGS[key] ?? key, vars);
}

/** `LanguageInfo.name_en` for the tag; `x-` / unknown tags keep the typed name. */
export function languageNameEn(tag: string, typedName?: string | null): string {
  return LANGUAGES[tag]?.name_en ?? typedName ?? tag;
}

export function clerkCardFromAnalysis(a: Pick<AnalysisResult, 'clerk_message'>, t: TFunction): ClerkCard {
  const extra = a.clerk_message.appended_line_keys.filter((k) => APPENDABLE.has(k));
  return {
    english: [a.clerk_message.english, ...extra.map((k) => english(k))].filter((l) => l.trim().length > 0),
    translated: [a.clerk_message.translated, ...extra.map((k) => t(k))].filter(Boolean).join(' '),
    ownWords: false,
  };
}

/** The need line in English (for the card) and in the UI language (for the user). */
export function needLines(need: ClerkNeed, t: TFunction): { en: string; ui: string } {
  if (need.kind === 'preset') return { en: english(`clerk.preset.${need.preset}`), ui: t(`clerk.preset.${need.preset}`) };
  if (need.kind === 'own') {
    const text = need.text.trim().slice(0, CLERK_OWN_WORDS_MAX);
    if (text) return { en: text, ui: text };
  }
  return { en: english('clerk.generic_need'), ui: t('clerk.generic_need') };
}

/** Generic card (no analysis, `/result/generic/clerk`): no interpreter line is ever appended. */
export function genericClerkCard(uiTag: string, need: ClerkNeed, t: TFunction): ClerkCard {
  const lines = needLines(need, t);
  const nameEn = languageNameEn(uiTag);
  const nameUi = LANGUAGES[uiTag]?.name_native ?? nameEn;
  return {
    english: [english('clerk.generic_card', { language: nameEn, need: lines.en })],
    translated: t('clerk.generic_card', { language: nameUi, need: lines.ui }),
    ownWords: need.kind === 'own' && need.text.trim().length > 0,
  };
}

/** Plain text for "Copy text" (English card only). */
export function clerkCopyText(card: ClerkCard): string {
  return card.english.join('\n');
}
