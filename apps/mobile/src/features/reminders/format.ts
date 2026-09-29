// Date/time wording for the reminders list. Uses the device's Intl in the UI language and falls
// back to `YYYY-MM-DD 09:00` when Intl cannot format that language. Verbatim dates from the paper
// are never re-formatted here (they are shown as printed, in <Bidi>).

import { toIsoDay } from './schedule';

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

export function formatFireTime(iso: string, languageTag: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  try {
    const day = d.toLocaleDateString(languageTag, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    const time = d.toLocaleTimeString(languageTag, { hour: 'numeric', minute: '2-digit' });
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
    const text = d.toLocaleDateString(languageTag, { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    if (text) return text;
  } catch {
    // numeric fallback below
  }
  return isoDay.slice(0, 10);
}
