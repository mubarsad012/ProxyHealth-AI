// Names for language tags that appear in resource entries' `languages` (the "Speaks: …" line,
// RESOURCE_DB §3) but have no row in `data/languages.yaml`, so no pack and no place in the S1
// language grid (the grid lists only `LANGUAGE_TAGS` and server languages). Without these the
// line printed the raw tag ("zh, hmn, km"). `apps/api/tests/unit/test_resource_language_names.py`
// fails when a resource lists a tag that is neither in the seed nor here.

import type { LanguageInfo } from '@/api/types';

export interface LanguageNames {
  name_native: string;
  name_en: string;
}

export const EXTRA_LANGUAGE_NAMES: Readonly<Record<string, LanguageNames>> = {
  hmn: { name_native: 'Hmoob', name_en: 'Hmong' },
  it: { name_native: 'Italiano', name_en: 'Italian' },
  km: { name_native: 'ខ្មែរ', name_en: 'Khmer' },
  kn: { name_native: 'ಕನ್ನಡ', name_en: 'Kannada' },
  pt: { name_native: 'Português', name_en: 'Portuguese' },
  ta: { name_native: 'தமிழ்', name_en: 'Tamil' },
  yue: { name_native: '粵語', name_en: 'Cantonese' },
  zh: { name_native: '中文', name_en: 'Chinese' },
};

/** `LanguageInfo` for a names-only tag (left-to-right, system font, Tier 3, no pack); else null. */
export function extraLanguageInfo(tag: string): LanguageInfo | null {
  const names = Object.prototype.hasOwnProperty.call(EXTRA_LANGUAGE_NAMES, tag) ? EXTRA_LANGUAGE_NAMES[tag] : null;
  if (!names) return null;
  return {
    tag,
    name_native: names.name_native,
    name_en: names.name_en,
    direction: 'ltr',
    script: null,
    digit_system: 'western',
    font_hint: null,
    tier: 3,
    bundled: false,
    machine_translated: true,
    tts_tag: null,
    tts_fallback_tag: null,
  };
}
