// Quick-sheet text builder (PRODUCT_SPEC S15, D-10). Pure: everything printed comes from the
// `AnalysisResult` (server-verified text, the paper's own words) or from vetted resource-DB entries
// (`Resource`, never model output). Contacts the server's filter stripped are never re-added.
// The sheet leaves the app (print, PDF, copy, read-aloud), so its header carries the same fixed
// `disclaimer.<disclaimer_kind>` line as S7 (PRODUCT_SPEC §5.6 "header of S7/S9/S15"), in the
// sheet's language with the English line under it for the clerk.

import type {
  AnalysisResult,
  ChecklistItem,
  QuickSheetRequest,
  QuickSheetResource,
  QuickSheetSection,
  Resource,
} from '@/api/types';
import { disclaimerKey } from '@/features/help/format';
import { stripIsolates } from '@/i18n/bidi';
import { BASE_STRINGS, translate } from '@/i18n/store';

import { buildAllowList, formatPhone, scrubLine, transcriptOf } from './contacts';

export type TranslateFn = (key: string, vars?: Record<string, string | number>) => string;

export type QuickSheetSectionKind = 'what' | 'asking' | 'plan' | 'dates' | 'bring' | 'help' | 'questions';

export interface QuickSheetText {
  title: string;
  /** Fixed `disclaimer.<kind>` line in the sheet's language (header, under the title). */
  disclaimer?: string;
  /** The same line in English (for the clerk); shown only when it differs from `disclaimer`. */
  disclaimer_en?: string;
  sections: QuickSheetSection[];
  footer: string;
  /** Parallel to `sections` (which card each one came from). */
  sectionKinds?: QuickSheetSectionKind[];
  /** Resource-DB entries exactly as stored (the PDF server re-validates them). */
  resources?: QuickSheetResource[];
}

export interface BuildQuickSheetOptions {
  /** English lookup for `heading_en` (defaults to the bundled English pack). */
  tEn?: TranslateFn;
  /** `YYYY-MM-DD` for the footer (defaults to today, local time). */
  today?: string;
  /** Checklist items from `ResourceMatch.checklist` (includes the per-document-type additions). */
  checklist?: ChecklistItem[];
}

export const MAX_SECTIONS = 8;
export const MAX_LINES = 40;
export const MAX_RESOURCES = 8;
export const MAX_TITLE = 120;
export const STRIPPED_MARKER_KEYS = ['warning.contacts_stripped_inline', 'warning.org_removed_inline'] as const;

const HEADING_KEYS: Record<QuickSheetSectionKind, string> = {
  what: 'card.what_is_this',
  asking: 'card.asking_for',
  plan: 'card.plan',
  dates: 'quicksheet.dates',
  bring: 'quicksheet.bring',
  help: 'quicksheet.help',
  questions: 'quicksheet.questions',
};

export const englishT: TranslateFn = (key, vars) => translate(BASE_STRINGS, key, vars);

export function todayIso(now: Date = new Date()): string {
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, '0');
  const d = String(now.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

/** `t` returns the key itself when a key is missing everywhere; treat that as "no copy". */
function copyOrNull(t: TranslateFn, key: string): string | null {
  const s = t(key);
  return s && s !== key ? s : null;
}

function uniq(lines: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const l of lines) {
    const k = l.trim().toLowerCase();
    if (!k || seen.has(k)) continue;
    seen.add(k);
    out.push(l.trim());
  }
  return out;
}

function truncate(lines: string[], t: TranslateFn): string[] {
  if (lines.length <= MAX_LINES) return lines;
  return [...lines.slice(0, MAX_LINES - 1), t('quicksheet.truncated')];
}

function dedupeResources(resources: Resource[]): Resource[] {
  const seen = new Set<string>();
  const out: Resource[] = [];
  for (const r of resources) {
    if (!r || seen.has(r.id) || r.link_health === 'broken') continue;
    seen.add(r.id);
    out.push(r);
  }
  return out.slice(0, MAX_RESOURCES);
}

/**
 * One line per verified dated demand. The label is the date exactly as PRINTED (`value_verbatim`);
 * the server's `localized_line` (e.g. Persian digits) is only ever ADDED after it in parentheses,
 * never substituted for it (D-26) — the clerk and the user must see the same date the paper shows.
 * A demand with no printed value gets no date label (a localized line alone is never a label).
 */
export function dateLines(analysis: AnalysisResult, t: TranslateFn): string[] {
  const out: string[] = [];
  for (const d of analysis.demands ?? []) {
    if (!d.verified) continue;
    const dated = d.date !== null || d.kind === 'deadline' || d.kind === 'relative_deadline' || d.kind === 'appointment';
    if (!dated) continue;
    const printed = (d.value_verbatim ?? '').trim();
    if (!printed) continue;
    let label = printed;
    if (d.date?.kind === 'estimated') label = `${t('demand.estimate_prefix')} ${label}`;
    const time = d.date?.time_text?.trim();
    if (time && !printed.includes(time)) label = `${label} ${time}`;
    const localized = (d.date?.localized_line ?? '').trim();
    const extra = localized && localized !== printed && !d.text.includes(localized) ? ` (${localized})` : '';
    out.push(d.text.includes(label) ? `${d.text}${extra}` : `${label}${extra} — ${d.text}`);
  }
  return out;
}

function bringLines(analysis: AnalysisResult, resources: Resource[], t: TranslateFn, checklist?: ChecklistItem[]): string[] {
  const out: string[] = [];
  for (const d of analysis.demands ?? []) {
    if (d.verified) out.push(...(d.documents ?? []));
  }
  // The matcher's per-result checklist (it already adds the document-type items) wins; the raw
  // `prepare_checklist_keys` of every listed resource are only a fallback, because national
  // fallbacks (e.g. an immigration line on a Medicaid letter) would add unrelated items.
  const keys: { key: string; textEn: string | null }[] = [];
  if (checklist) {
    for (const item of checklist) keys.push({ key: item.key, textEn: item.text_en });
  } else {
    for (const r of resources) for (const key of r.prepare_checklist_keys ?? []) keys.push({ key, textEn: null });
  }
  for (const { key, textEn } of keys) {
    const text = copyOrNull(t, `prepare.${key}`) ?? textEn;
    if (text) out.push(text);
  }
  return out;
}

function helpLines(resources: Resource[]): string[] {
  return resources.map((r) => {
    if (r.phone) return `${r.name} — ${formatPhone(r.phone)}`;
    return r.url ? `${r.name} — ${r.url}` : r.name;
  });
}

/**
 * Build the quick sheet from an analysis and its matched resources. Anything not in `analysis`
 * or in the resource DB is excluded; stripped-contact markers are removed, never replaced.
 */
export function buildQuickSheetText(
  analysis: AnalysisResult,
  resources: Resource[],
  tUi: TranslateFn,
  opts: BuildQuickSheetOptions = {},
): QuickSheetText {
  // The sheet is plain text for print, PDF, copy and read-aloud: no UI bidi isolates (`useT` adds
  // FSI…PDI around all-LTR strings in RTL packs); the HTML and the PDF isolate runs themselves.
  const t: TranslateFn = (key, vars) => stripIsolates(tUi(key, vars));
  const tEn = opts.tEn ?? englishT;
  const dbResources = dedupeResources(resources ?? []);
  const allow = buildAllowList(transcriptOf(analysis), dbResources);
  const markers = uniq(STRIPPED_MARKER_KEYS.flatMap((k) => [t(k), tEn(k)]).filter((m) => m && !m.startsWith('warning.')));
  const clean = (lines: string[]): string[] =>
    uniq(lines.map((l) => scrubLine(l, allow, markers)).filter((l): l is string => l !== null));

  const raw: [QuickSheetSectionKind, string[]][] = [];
  const what: string[] = [];
  if (analysis.summary?.body) what.push(analysis.summary.body);
  if (analysis.sender_as_written) what.push(t('card.sender_as_written', { sender: analysis.sender_as_written }));
  raw.push(['what', what]);
  const asking = (analysis.demands ?? []).filter((d) => d.verified).map((d) => d.text);
  raw.push(['asking', asking.length ? asking : [t('card.asking_nothing')]]);
  raw.push(['plan', (analysis.plan_steps ?? []).map((s) => s.text)]);
  raw.push(['dates', dateLines(analysis, t)]);
  raw.push(['bring', bringLines(analysis, dbResources, t, opts.checklist)]);
  raw.push(['help', helpLines(dbResources)]);
  raw.push(['questions', analysis.questions_to_ask ?? []]);

  const sections: QuickSheetSection[] = [];
  const sectionKinds: QuickSheetSectionKind[] = [];
  for (const [kind, lines] of raw) {
    // Resource lines are DB entries verbatim ("211 — 211" has no letters); everything else is scrubbed.
    let kept = kind === 'help' ? uniq(lines) : clean(lines);
    if (kind === 'plan') kept = kept.map((l, i) => `${i + 1}. ${l}`);
    if (!kept.length) continue;
    sections.push({ heading: t(HEADING_KEYS[kind]), heading_en: tEn(HEADING_KEYS[kind]), lines: truncate(kept, t) });
    sectionKinds.push(kind);
  }

  const baseTitle = scrubLine(analysis.summary?.title ?? '', allow, markers) ?? '';
  const title = `${baseTitle} ${t('quicksheet.title_suffix')}`.trim().slice(0, MAX_TITLE);
  // Banner-only kinds (`demo_sample`, `machine_translation`…) fall back to the general line.
  const dKey = disclaimerKey(analysis.disclaimer_kind);
  return {
    title,
    disclaimer: t(dKey),
    disclaimer_en: tEn(dKey),
    sections: sections.slice(0, MAX_SECTIONS),
    sectionKinds: sectionKinds.slice(0, MAX_SECTIONS),
    footer: t('quicksheet.footer', { date: opts.today ?? todayIso() }),
    resources: dbResources.map((r) => ({ name: r.name, phone: r.phone ?? null, url: r.url ?? null })),
  };
}

/** Plain text for "Copy text" and "Read aloud" (headings in the UI language, English under them). */
export function quickSheetPlainText(sheet: QuickSheetText, opts: { includeEnglishHeadings?: boolean } = {}): string {
  const english = opts.includeEnglishHeadings ?? true;
  const parts: string[] = [sheet.title];
  if (sheet.disclaimer) {
    const en = english && sheet.disclaimer_en && sheet.disclaimer_en !== sheet.disclaimer ? sheet.disclaimer_en : null;
    parts.push(['', sheet.disclaimer, ...(en ? [en] : [])].join('\n'));
  }
  for (const s of sheet.sections) {
    const head = english && s.heading_en && s.heading_en !== s.heading ? `${s.heading} (${s.heading_en})` : s.heading;
    parts.push(['', head, ...s.lines].join('\n'));
  }
  parts.push(['', sheet.footer].join('\n'));
  return parts.join('\n');
}

export interface QuickSheetMeta {
  languageTag: string;
  direction: 'ltr' | 'rtl';
  fontHint: string | null;
  /** `YYYY-MM-DD`. */
  generatedOn?: string;
}

/**
 * The `POST /v1/quicksheet/pdf` body. The "Who can help" lines travel as `resources` (the server
 * re-validates each against the DB and renders them itself), so that section is sent as a heading
 * carrier only — its localized `heading` and English `heading_en` with no lines — which the server
 * uses as the resources heading and never draws as a section of its own (`render.help_heading`).
 * The contract has no disclaimer field, so the header disclaimer travels as the FIRST section with
 * no lines: the server draws it right under the title, in the sheet's language with the English
 * line under it (`render._heading`).
 */
export function toQuickSheetRequest(sheet: QuickSheetText, meta: QuickSheetMeta): QuickSheetRequest {
  const hasResources = Boolean(sheet.resources?.length);
  const content = sheet.sections.map((s, i) =>
    sheet.sectionKinds?.[i] === 'help' && hasResources ? { ...s, lines: [] } : s,
  );
  const header: QuickSheetSection[] = sheet.disclaimer
    ? [{ heading: sheet.disclaimer, heading_en: sheet.disclaimer_en || sheet.disclaimer, lines: [] }]
    : [];
  const sections = [...header, ...content];
  return {
    title: sheet.title.slice(0, MAX_TITLE),
    language_tag: meta.languageTag,
    direction: meta.direction,
    font_hint: meta.fontHint,
    sections: sections.slice(0, MAX_SECTIONS).map((s) => ({ ...s, lines: s.lines.slice(0, MAX_LINES) })),
    resources: (sheet.resources ?? []).slice(0, MAX_RESOURCES),
    footer: sheet.footer,
    generated_on: meta.generatedOn ?? todayIso(),
  };
}
