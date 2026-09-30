// Display helpers for resource cards (PRODUCT_SPEC S11). Pure; copy comes from pack keys.

import type { Cost, LinkHealth, Resource } from '@/api/types';
import { formatPhone } from '@/features/quicksheet/contacts';
import { BASE_STRINGS, keyExists, languageInfoFor } from '@/i18n/store';

export type T = (key: string, vars?: Record<string, string | number>) => string;

export const STALE_DAYS = 120;

export const COST_KEYS: Record<Cost, string> = {
  free: 'resource.free',
  sliding: 'resource.sliding',
  paid: 'resource.paid',
  unknown: 'resource.unknown_cost',
};

/** Extra line under "Verified on" for link-health variants (`ok` → none; `broken` → hidden card). */
export function linkNoteKey(health: LinkHealth): string | null {
  if (health === 'unknown_403' || health === 'js_rendered') return 'resource.link_unknown';
  if (health === 'unverified') return 'resource.link_unverified';
  return null;
}

export function daysBetween(fromIso: string, now: Date): number {
  const from = Date.parse(`${fromIso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(from)) return 0;
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.floor((today - from) / 86_400_000);
}

export function isStale(verifiedOn: string, now: Date = new Date()): boolean {
  return daysBetween(verifiedOn, now) > STALE_DAYS;
}

/**
 * Pack key for a result's fixed disclaimer. `DisclaimerKind` also carries banner-only kinds
 * (`machine_translation`, `demo_sample`…) that have no `disclaimer.*` line; those fall back to
 * the general-information line so a raw key is never shown.
 */
export function disclaimerKey(kind: string | null | undefined): string {
  const key = `disclaimer.${kind ?? 'general_information'}`;
  return keyExists(key) ? key : 'disclaimer.general_information';
}

export function isVisible(resource: Resource): boolean {
  return resource.link_health !== 'broken';
}

/** `what_it_does[language] ?? en`, with a flag when the English fallback was used ("EN" chip). */
export function localized(dict: Record<string, string> | null | undefined, lang: string): { text: string; english: boolean } | null {
  if (!dict) return null;
  const own = dict[lang] ?? dict[lang.split('-')[0]];
  if (own) return { text: own, english: lang === 'en' };
  if (dict.en) return { text: dict.en, english: lang !== 'en' };
  return null;
}

/** "Speaks: …" (native names) or the interpreters line. */
export function languagesLine(languages: readonly string[], t: T): string | null {
  if (!languages.length) return null;
  if (languages.includes('interpreters_200+')) return t('resource.interpreters');
  const names = languages.map((tag) => languageInfoFor(tag).name_native || tag);
  return t('resource.languages', { list: names.join(', ') });
}

/** Screen-reader label: "Call {organization}, 2 1 1" (digits grouped so they are read one by one). */
export function callLabel(resource: Resource, t: T, phone: string = resource.phone ?? ''): string {
  const digits = formatPhone(phone)
    .replace(/[^\d-]/g, ' ')
    .split(/[\s-]+/)
    .filter(Boolean)
    .map((group) => group.split('').join(' '))
    .join(', ');
  return `${t('btn.call')} ${resource.name}, ${digits}`;
}

/** `tel:` link for a DB phone (E.164 or N11). */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, '')}`;
}

export function prepareText(key: string, textEn: string, t: T): string | null {
  const k = `prepare.${key}`;
  const s = t(k);
  if (s && s !== k) return s;
  return textEn || null;
}

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Recover `{placeholder}` values from the server's English `why` line by matching it against the
 * English template (e.g. "Serves {state}" vs "Serves Virginia" → { state: "Virginia" }).
 */
export function whyVars(key: string, rendered: string | undefined): Record<string, string> | null {
  const template = BASE_STRINGS[key];
  if (!template || !rendered) return null;
  const names: string[] = [];
  const pattern = template
    .split(/(\{[A-Za-z_][A-Za-z0-9_]*\})/)
    .map((part) => {
      const m = /^\{([A-Za-z_][A-Za-z0-9_]*)\}$/.exec(part);
      if (!m) return escapeRegExp(part);
      names.push(m[1]);
      return '(.+?)';
    })
    .join('');
  const hit = new RegExp(`^${pattern}$`).exec(rendered.trim());
  if (!hit) return null;
  return Object.fromEntries(names.map((n, i) => [n, hit[i + 1]]));
}

/** Localized why-chip; falls back to the server's English line when a value cannot be filled. */
export function whyText(key: string, fallback: string | undefined, t: T): string | null {
  const template = BASE_STRINGS[key];
  const needsVars = Boolean(template && /\{[A-Za-z_]/.test(template));
  if (needsVars) {
    const vars = whyVars(key, fallback);
    if (vars) return t(key, vars);
    return fallback || null;
  }
  const s = t(key);
  if (s && s !== key) return s;
  return fallback || null;
}

export { formatPhone };
