// Client-side belt-and-braces contact guard for the quick sheet (D-10, PRODUCT_SPEC S15).
// The server's contacts filter already replaced invented phones/URLs/e-mails in model text with
// the `warning.contacts_stripped_inline` marker. The quick sheet is printed and handed to people,
// so it must never re-add a stripped contact: markers are removed, and any phone / URL / e-mail
// that is neither on the paper (the transcript) nor in a vetted resource-DB entry is dropped.
// Pure functions; nothing here is logged or stored.

import type { AnalysisResult, Resource } from '@/api/types';

const EMAIL_RE = /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g;
const URL_RE =
  /(?:https?:\/\/[^\s<>"')\]]+)|(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:gov|org|com|net|us|edu|info|mil|io|co)\b(?:\/[^\s<>"')\]]*)?/gi;
// A digit run with phone punctuation. Classified by digit count below (dates such as 10-14-2026
// have 8 digits and are not phones). The optional leading group keeps "IOE0912345678" whole.
const PHONE_RE = /(^|[^A-Za-z0-9])(\+?\(?\d[\d\s().-]{5,}\d)/g;
const N11 = new Set(['211', '311', '911', '988', '711']);

export function digitsOnly(text: string): string {
  return text.replace(/\D+/g, '');
}

/** Normalise a phone to its last 10 digits (NANP) or all digits (short / international). */
export function normalizePhone(text: string): string {
  const d = digitsOnly(text);
  if (d.length === 11 && d.startsWith('1')) return d.slice(1);
  return d;
}

export function normalizeUrl(text: string): string {
  return text
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^www\./, '')
    .replace(/[/.,;:!?]+$/, '');
}

function isPhoneLike(candidate: string): boolean {
  const n = digitsOnly(candidate).length;
  if (n >= 10 && n <= 15) return true;
  return n === 7 && /^\d{3}[-.\s]\d{4}$/.test(candidate.trim());
}

export interface ContactAllowList {
  phones: Set<string>;
  urls: Set<string>;
  emails: Set<string>;
}

/** All words of the paper as read (transcript blocks), for the "on the paper" test. */
export function transcriptOf(analysis: AnalysisResult): string {
  const parts: string[] = [];
  for (const page of analysis.original_text ?? []) {
    for (const block of page.blocks ?? []) parts.push(block.text);
  }
  return parts.join('\n');
}

export function buildAllowList(transcript: string, resources: Resource[]): ContactAllowList {
  const phones = new Set<string>();
  const urls = new Set<string>();
  const emails = new Set<string>();
  for (const m of transcript.matchAll(PHONE_RE)) {
    if (isPhoneLike(m[2])) phones.add(normalizePhone(m[2]));
  }
  for (const m of transcript.matchAll(URL_RE)) urls.add(normalizeUrl(m[0]));
  for (const m of transcript.matchAll(EMAIL_RE)) emails.add(m[0].toLowerCase());
  for (const r of resources) {
    if (r.phone) phones.add(normalizePhone(r.phone));
    if (r.tty) phones.add(normalizePhone(r.tty));
    if (r.url) urls.add(normalizeUrl(r.url));
    for (const alt of r.alt_urls ?? []) urls.add(normalizeUrl(alt));
  }
  return { phones, urls, emails };
}

function tidy(text: string): string {
  return text
    .replace(/\(\s*\)|\[\s*\]/g, '')
    .replace(/\s+([,.;:!?،؛])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/**
 * Remove stripped-contact markers and any contact not on the allow list. Returns `null` when
 * nothing readable is left (the line is dropped).
 */
export function scrubLine(line: string, allow: ContactAllowList, markers: readonly string[]): string | null {
  let out = line;
  for (const marker of markers) {
    if (marker) out = out.split(marker).join(' ');
  }
  out = out.replace(EMAIL_RE, (m) => (allow.emails.has(m.toLowerCase()) ? m : ' '));
  out = out.replace(URL_RE, (m) => {
    if (m.includes('@')) return m;
    return allow.urls.has(normalizeUrl(m)) ? m : ' ';
  });
  out = out.replace(PHONE_RE, (whole, lead: string, num: string) => {
    if (!isPhoneLike(num)) return whole;
    return allow.phones.has(normalizePhone(num)) ? whole : `${lead} `;
  });
  out = tidy(out);
  // Keep a line only if some letters survive (a lone "Call" or "." is noise on paper).
  // (No \p{…} classes: keep the regex portable across Hermes and JSC.)
  const letters = out.replace(/[\s\d!-/:-@[-`{-~«»“”‘’…—–·•،؛؟]/g, '');
  return letters.length >= 2 ? out : null;
}

/** True for bare N11 codes (211, 988…) the resource DB may carry as `phone`. */
export function isN11(phone: string): boolean {
  return N11.has(phone.trim());
}

/** US toll-free area codes (printed "1-800-…", as the papers and hotlines print them). */
export const TOLL_FREE_AREA_CODES: ReadonlySet<string> = new Set(['800', '833', '844', '855', '866', '877', '888']);
const NANP = /^(?:\+?1)?([2-9]\d{2})([2-9]\d{2})(\d{4})$/;

/**
 * Display form of a DB phone, the same rule as the PDF (`quicksheet/render.py` `format_phone`):
 * toll free "+18003182596" → "1-800-318-2596", other US "+15714725880" → "(571) 472-5880"; N11
 * codes, extensions and non-US numbers unchanged. Every national digit is kept; `tel:` links keep
 * using the stored E.164 value (`features/help/format.ts` `telHref`).
 */
export function formatPhone(phone: string): string {
  const p = phone.trim();
  if (isN11(p)) return p;
  const m = NANP.exec(p.replace(/[\s().-]/g, ''));
  if (!m) return p;
  const [, area, exchange, line] = m;
  return TOLL_FREE_AREA_CODES.has(area) ? `1-${area}-${exchange}-${line}` : `(${area}) ${exchange}-${line}`;
}
