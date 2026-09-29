// Device-locale → bundled/known tag matching (PRODUCT_SPEC S1 "device-locale chip preselected").
// expo-localization works on web (navigator.languages); every call is guarded because the static
// web export runs this code in Node where `navigator` does not exist.
// Verified against https://docs.expo.dev/versions/v57.0.0/sdk/localization/ : getLocales()[0]
// → { languageTag, languageCode, languageScriptCode, regionCode, textDirection }.

import { getLocales } from 'expo-localization';

import { LANGUAGE_TAGS } from '@/i18n/languages';

export interface DeviceLocale {
  languageTag: string;
  languageCode: string | null;
  scriptCode: string | null;
  regionCode: string | null;
  textDirection: 'ltr' | 'rtl' | null;
}

export function deviceLocale(): DeviceLocale | null {
  try {
    const first = getLocales()[0];
    if (!first) return null;
    return {
      languageTag: first.languageTag,
      languageCode: first.languageCode ?? null,
      scriptCode: first.languageScriptCode ?? null,
      regionCode: first.regionCode ?? null,
      textDirection: first.textDirection ?? null,
    };
  } catch {
    return null;
  }
}

/** Aliases the seed spells differently from what devices report. */
const ALIASES: Record<string, string> = {
  fil: 'tl',
  'zh-CN': 'zh-Hans',
  'zh-SG': 'zh-Hans',
  'zh-TW': 'zh-Hant',
  'zh-HK': 'zh-Hant',
  'zh-MO': 'zh-Hant',
  pt: 'pt-BR',
  'fa-AF': 'prs',
};

/**
 * Pick the known tag that best matches a BCP-47 locale tag: exact match, alias, language+script,
 * then bare language code. Returns null when nothing matches (the grid then preselects nothing).
 */
export function matchTagForLocale(
  locale: string | DeviceLocale | null | undefined,
  known: readonly string[] = LANGUAGE_TAGS,
): string | null {
  if (!locale) return null;
  const tag = typeof locale === 'string' ? locale : locale.languageTag;
  if (!tag) return null;
  const knownSet = new Set(known);
  if (knownSet.has(tag)) return tag;
  if (ALIASES[tag] && knownSet.has(ALIASES[tag])) return ALIASES[tag];
  const parts = tag.split('-');
  const lang = parts[0].toLowerCase();
  const script = typeof locale === 'object' ? locale.scriptCode : parts.find((p) => p.length === 4);
  const region = typeof locale === 'object' ? locale.regionCode : parts.find((p) => p.length === 2 && p !== lang);
  if (lang === 'zh') {
    if (script === 'Hant' || (region && ['TW', 'HK', 'MO'].includes(region))) {
      return knownSet.has('zh-Hant') ? 'zh-Hant' : null;
    }
    return knownSet.has('zh-Hans') ? 'zh-Hans' : null;
  }
  if (region && knownSet.has(`${lang}-${region}`)) return `${lang}-${region}`;
  if (script && knownSet.has(`${lang}-${script}`)) return `${lang}-${script}`;
  if (knownSet.has(lang)) return lang;
  if (ALIASES[lang] && knownSet.has(ALIASES[lang])) return ALIASES[lang];
  for (const k of known) {
    if (k.split('-')[0] === lang) return k;
  }
  return null;
}

/** The tag to preselect on S1 for this device (null when the device language is not bundled). */
export function suggestedTag(): string | null {
  return matchTagForLocale(deviceLocale());
}
