// S1 language grid data (PRODUCT_SPEC S1): native name first, English name beneath; order en, es, ps,
// prs, ar (the blueprint's five), then the remaining Tier 1 in seed order (community size), then
// Tier 2, then Tier 3 seed entries (generated on demand). Server languages extend the bundled
// seed when `/v1/config` is reachable; offline the seed alone is used.

import type { LanguageInfo } from '@/api/types';
import { LANGUAGE_TAGS, LANGUAGES } from '@/i18n/languages';
import { bundledPackFor } from '@/i18n/store';

export const PINNED_FIRST: readonly string[] = ['en', 'es', 'ps', 'prs', 'ar'];

export interface GridLanguage extends LanguageInfo {
  /** A pack file ships in the app (works offline). */
  offline: boolean;
}

export function gridLanguages(server: LanguageInfo[] | null | undefined): GridLanguage[] {
  const byTag = new Map<string, LanguageInfo>();
  for (const tag of LANGUAGE_TAGS) {
    const info = LANGUAGES[tag];
    if (info) byTag.set(tag, info);
  }
  for (const info of server ?? []) {
    byTag.set(info.tag, { ...byTag.get(info.tag), ...info });
  }
  const seedIndex = (tag: string) => {
    const i = LANGUAGE_TAGS.indexOf(tag);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  const all = [...byTag.values()];
  const pinned = PINNED_FIRST.map((t) => byTag.get(t)).filter((x): x is LanguageInfo => Boolean(x));
  const rest = all
    .filter((l) => !PINNED_FIRST.includes(l.tag))
    .sort((a, b) => a.tier - b.tier || seedIndex(a.tag) - seedIndex(b.tag) || a.name_en.localeCompare(b.name_en));
  return [...pinned, ...rest].map((l) => ({ ...l, offline: l.tag === 'en' || Boolean(bundledPackFor(l.tag)) }));
}

/** Put the device-suggested language first (S1 "Suggested for this phone" chip). */
export function withSuggestionFirst(list: GridLanguage[], suggested: string | null): {
  suggested: GridLanguage | null;
  others: GridLanguage[];
} {
  const s = suggested ? list.find((l) => l.tag === suggested) ?? null : null;
  return { suggested: s, others: s ? list.filter((l) => l.tag !== s.tag) : list };
}

/** Typed-box rule: enabled at ≥ 2 characters (PRODUCT_SPEC S1 primary action). */
export function typedQueryUsable(q: string): boolean {
  return q.trim().length >= 2;
}

/** A typed query that exactly names a known language (native or English name, or its tag). */
export function matchTyped(list: GridLanguage[], q: string): GridLanguage | null {
  const needle = q.trim().toLowerCase();
  if (!needle) return null;
  return (
    list.find(
      (l) => l.tag.toLowerCase() === needle || l.name_en.toLowerCase() === needle || l.name_native.toLowerCase() === needle,
    ) ?? null
  );
}
