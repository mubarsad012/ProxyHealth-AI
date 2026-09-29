// Localized *additional* numeral line (D-26, PRODUCT_SPEC §5.2 rule 2). Verbatim values are never
// replaced: these helpers produce a second line the UI may show under the printed value.

import type { DigitSystem } from '@/api/types';

/** Positional digit sets. Ethiopic numerals are not positional and `other` is unknown → null. */
export const DIGIT_SETS: Record<DigitSystem, string | null> = {
  western: '0123456789',
  eastern_arabic: '٠١٢٣٤٥٦٧٨٩',
  persian: '۰۱۲۳۴۵۶۷۸۹',
  devanagari: '०१२३४५६७८९',
  bengali: '০১২৩৪৫৬৭৮৯',
  gurmukhi: '੦੧੨੩੪੫੬੭੮੯',
  myanmar: '၀၁၂၃၄၅၆၇၈၉',
  ethiopic: null,
  other: null,
};

/** Replace Western digits with the pack's digits. Returns the input unchanged for western/null. */
export function toLocalizedDigits(text: string, system: DigitSystem): string {
  const set = DIGIT_SETS[system];
  if (!set || system === 'western') return text;
  return text.replace(/[0-9]/g, (d) => set[Number(d)] ?? d);
}

/** True when a system has digits that differ from Western ones. */
export function hasDistinctDigits(system: DigitSystem): boolean {
  return system !== 'western' && DIGIT_SETS[system] !== null;
}

export type DateOrder = 'auto' | 'mdy' | 'dmy';

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})/;

/**
 * Localized date line for an ISO date (`YYYY-MM-DD…`). Returns `null` when the pack uses Western
 * digits (nothing to add) or the input is not an ISO date. The order follows the user's
 * `dateFormat` preference; `auto` keeps day-month-year, the order most bundled RTL/Indic
 * communities read (the verbatim printed date is always shown above this line anyway).
 */
export function localizedDateLine(
  iso: string | null | undefined,
  system: DigitSystem,
  order: DateOrder = 'auto',
): string | null {
  if (!iso || !hasDistinctDigits(system)) return null;
  const m = ISO_DATE.exec(iso);
  if (!m) return null;
  const [, y, mo, d] = m;
  const day = String(Number(d));
  const month = String(Number(mo));
  const western = order === 'mdy' ? `${month}/${day}/${y}` : `${day}/${month}/${y}`;
  return toLocalizedDigits(western, system);
}

/** Localized rendering of a plain number (amounts stay verbatim; this is an extra line). */
export function localizedNumberLine(value: number | string, system: DigitSystem): string | null {
  if (!hasDistinctDigits(system)) return null;
  return toLocalizedDigits(String(value), system);
}
