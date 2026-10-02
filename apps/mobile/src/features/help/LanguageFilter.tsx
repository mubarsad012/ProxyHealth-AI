// S11 language filter chip ("Speaks: {language}", default = the UI language). Collapsed it is one
// chip-like row that names the current choice; open it lists every app language (native names)
// and "Any language". The choice is sent as `language` to the match / browse requests
// (`browse.ts` `matchLanguage` / `browseLanguage`), never stored.

import { ChoiceChips, Collapsible } from '@/design/components';
import { languageInfoFor } from '@/i18n/store';
import { useT } from '@/i18n/useT';

import { ANY_LANGUAGE, languageFilterTags } from './browse';

export const ANY_LANGUAGE_KEY = 'help.any_language';

export interface LanguageFilterProps {
  /** A language tag or `ANY_LANGUAGE`. */
  value: string;
  /** The UI language (the default choice, listed first). */
  uiTag: string;
  onChange(tag: string): void;
}

export function languageLabel(tag: string, t: (key: string, vars?: Record<string, string | number>) => string): string {
  if (tag === ANY_LANGUAGE) return t(ANY_LANGUAGE_KEY);
  const info = languageInfoFor(tag);
  return info.name_native || info.name_en || tag;
}

export function LanguageFilter({ value, uiTag, onChange }: LanguageFilterProps) {
  const t = useT();
  const title = value === ANY_LANGUAGE ? t(ANY_LANGUAGE_KEY) : t('resource.languages', { list: languageLabel(value, t) });
  // `key` remounts the row on a pick, so it closes and announces the new "Speaks: …" title.
  return (
    <Collapsible key={value} title={title}>
      <ChoiceChips<string>
        options={languageFilterTags(uiTag).map((tag) => ({ value: tag, label: languageLabel(tag, t) }))}
        value={value}
        onChange={onChange}
        testIDPrefix="help-language"
      />
    </Collapsible>
  );
}
