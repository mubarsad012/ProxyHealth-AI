// Date/time wording for the reminders list, the Home next-date card and the vault rows. Uses the
// device's Intl in the UI language and falls back to `YYYY-MM-DD 09:00` when Intl cannot format
// that language. Verbatim dates from the paper are never re-formatted here (they are shown as
// printed, in <Bidi>).
//
// Always the Gregorian calendar with Western digits (D-26: digits are never localized; a localized
// line may be added, never substituted). The papers are American and Gregorian: the default
// calendar for prs/ps/fa is Solar Hijri ("15 Mizan 1405") and for th Buddhist ("2569"), which the
// reader could not match against the paper or what the clerk says. The `-u-ca-gregory-nu-latn`
// extension plus the `calendar`/`numberingSystem` options ask for that; if an engine ignores them
// (the output lacks the Gregorian year) the numeric ISO form is used instead, and any localized
// digits that slip through are mapped back to Western ones.

import { DIGIT_SETS } from '@/i18n/digits';

import { toIsoDay } from './schedule';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

const GREGORIAN: Intl.DateTimeFormatOptions = { calendar: 'gregory', numberingSystem: 'latn' };
const DAY_OPTIONS: Intl.DateTimeFormatOptions = { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' };
const TIME_OPTIONS: Intl.DateTimeFormatOptions = { hour: 'numeric', minute: '2-digit' };

const LOCAL_DIGITS: ReadonlyMap<string, string> = new Map(
  Object.values(DIGIT_SETS)
    .filter((set): set is string => Boolean(set) && set !== DIGIT_SETS.western)
    .flatMap((set) => Array.from(set).map((ch, i) => [ch, String(i)] as const)),
);

/** Map Persian, Arabic-Indic, Devanagari, Bengali, Gurmukhi and Myanmar digits to 0–9. */
export function toWesternDigits(text: string): string {
  let out = '';
  for (const ch of text) out += LOCAL_DIGITS.get(ch) ?? ch;
  return out;
}

/** `prs` → `prs-u-ca-gregory-nu-latn` (a tag that already has a `-u-` extension is left alone). */
export function gregorianLocale(languageTag: string): string {
  const tag = (languageTag || 'en').trim() || 'en';
  return /-u-/i.test(tag) ? tag : `${tag}-u-ca-gregory-nu-latn`;
}

function formatGregorian(d: Date, languageTag: string, options: Intl.DateTimeFormatOptions): string | null {
  const fmt = new Intl.DateTimeFormat(gregorianLocale(languageTag), { ...options, ...GREGORIAN });
  const calendar = fmt.resolvedOptions().calendar;
  if (calendar && calendar !== 'gregory' && calendar !== 'iso8601') return null;
  const text = toWesternDigits(fmt.format(d));
  if (!text) return null;
  // An engine that ignored the calendar request prints another year (1405, 2569): not usable.
  if (options.year && !text.includes(String(d.getFullYear()))) return null;
  return text;
}

export function formatFireTime(iso: string, languageTag: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    const day = formatGregorian(d, languageTag, DAY_OPTIONS);
    const time = formatGregorian(d, languageTag, TIME_OPTIONS);
    if (day && time) return `${day}, ${time}`;
  } catch {
    // fall through to the numeric form
  }
  return `${toIsoDay(d)} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function formatDay(isoDay: string, languageTag: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDay);
  if (!m) return isoDay;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]), 12);
  try {
    const text = formatGregorian(d, languageTag, DAY_OPTIONS);
    if (text) return text;
  } catch {
    // numeric fallback below
  }
  return isoDay.slice(0, 10);
}

/** Wall-clock time only (e.g. Home `home.busy_until` "Try again at {time}"). */
export function formatClock(iso: string, languageTag: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    const time = formatGregorian(d, languageTag, TIME_OPTIONS);
    if (time) return time;
  } catch {
    // numeric fallback below
  }
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
