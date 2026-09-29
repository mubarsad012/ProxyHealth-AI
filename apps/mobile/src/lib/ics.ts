// RFC 5545 calendar builder for reminders (PRODUCT_SPEC §10.2 "Web", ARCHITECTURE §3.1).
// One VEVENT per reminder; DTSTART is the reminder's local wall-clock time as FLOATING time (no
// TZID, no trailing Z) so a calendar shows 9:00 wherever the phone is; SUMMARY is the generic
// sentence unless the user opted into detail; there is never a DESCRIPTION with paper content
// (the optional VALARM text is always the generic sentence). CRLF line endings, 75-octet folding,
// TEXT escaping per RFC 5545 §3.1 / §3.3.11. Pure: no platform imports (unit-tested).

export interface IcsEvent {
  /** Stable id for this reminder (becomes the UID). */
  uid: string;
  /** Local wall-clock start, written as floating time. */
  start: Date;
  /** Already-translated title shown in the calendar (generic unless detail opt-in). */
  summary: string;
  /** Event length in minutes (default 30). */
  durationMinutes?: number;
  /** When set, adds a display alarm at the start time carrying this (generic) text. */
  alarmText?: string;
}

export interface BuildIcsOptions {
  /** DTSTAMP source (defaults to now). */
  now?: Date;
  prodId?: string;
}

export const ICS_MIME = 'text/calendar';
const CRLF = '\r\n';
const DEFAULT_PRODID = '-//ProxyHealth AI//Reminders//EN';

function pad(n: number, width = 2): string {
  return String(n).padStart(width, '0');
}

/** `YYYYMMDDTHHMMSS` from the device-local components (floating time). */
export function formatFloating(d: Date): string {
  return (
    `${pad(d.getFullYear(), 4)}${pad(d.getMonth() + 1)}${pad(d.getDate())}` +
    `T${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
  );
}

/** `YYYYMMDDTHHMMSSZ` in UTC (DTSTAMP must be UTC). */
export function formatUtc(d: Date): string {
  return (
    `${pad(d.getUTCFullYear(), 4)}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}` +
    `T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`
  );
}

/** Escape a TEXT value: backslash, semicolon, comma and newlines (RFC 5545 §3.3.11). */
export function escapeText(value: string): string {
  return value
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n');
}

function utf8Length(ch: string): number {
  const code = ch.codePointAt(0) ?? 0;
  if (code < 0x80) return 1;
  if (code < 0x800) return 2;
  if (code < 0x10000) return 3;
  return 4;
}

/** Fold a content line at 75 octets; continuation lines start with one space (RFC 5545 §3.1).
 *  Never splits inside a UTF-8 character. */
export function foldLine(line: string): string {
  const out: string[] = [];
  let current = '';
  let octets = 0;
  let limit = 75;
  for (const ch of Array.from(line)) {
    const len = utf8Length(ch);
    if (octets + len > limit) {
      out.push(current);
      current = ' ';
      octets = 1;
      limit = 75;
    }
    current += ch;
    octets += len;
  }
  out.push(current);
  return out.join(CRLF);
}

/** UID-safe token (letters, digits, dash, underscore, dot). */
function uidToken(uid: string): string {
  const cleaned = uid.replace(/[^A-Za-z0-9._-]/g, '-');
  return cleaned.length > 0 ? cleaned : 'reminder';
}

function eventLines(e: IcsEvent, stamp: string): string[] {
  const minutes = Math.max(1, Math.round(e.durationMinutes ?? 30));
  const lines = [
    'BEGIN:VEVENT',
    `UID:proxyhealth-${uidToken(e.uid)}`,
    `DTSTAMP:${stamp}`,
    `DTSTART:${formatFloating(e.start)}`,
    `DURATION:PT${minutes}M`,
    `SUMMARY:${escapeText(e.summary)}`,
    'TRANSP:TRANSPARENT',
  ];
  if (e.alarmText) {
    lines.push('BEGIN:VALARM', 'ACTION:DISPLAY', `DESCRIPTION:${escapeText(e.alarmText)}`, 'TRIGGER:PT0M', 'END:VALARM');
  }
  lines.push('END:VEVENT');
  return lines;
}

/** A complete VCALENDAR with one VEVENT per event, CRLF-terminated. */
export function buildIcs(events: IcsEvent[], opts: BuildIcsOptions = {}): string {
  const stamp = formatUtc(opts.now ?? new Date());
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    `PRODID:${opts.prodId ?? DEFAULT_PRODID}`,
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
  ];
  for (const e of events) lines.push(...eventLines(e, stamp));
  lines.push('END:VCALENDAR');
  return lines.map(foldLine).join(CRLF) + CRLF;
}

/** Count of VEVENT blocks in an .ics text (tests and sanity checks). */
export function countEvents(ics: string): number {
  return (ics.match(/^BEGIN:VEVENT\r?$/gm) ?? []).length;
}

/** A calm, filesystem-safe file name, e.g. `proxyhealth-reminders.ics`. */
export function icsFileName(base = 'proxyhealth-reminders'): string {
  const safe = base.replace(/[^A-Za-z0-9_-]/g, '-').slice(0, 60) || 'reminders';
  return `${safe}.ics`;
}
