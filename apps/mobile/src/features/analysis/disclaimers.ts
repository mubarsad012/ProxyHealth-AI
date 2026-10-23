// Fixed-copy keys for disclaimers, banners and warning chips (PRODUCT_SPEC §5.6, D-17). The model
// never writes any of these; the client maps enum values to pack keys.

import type { AnalysisResult, DisclaimerKind, WarningCode } from '@/api/types';
import { languageName } from '@/features/speech/fallback';

/** Header disclaimer (S7 item 5) for the primary `disclaimer_kind`; null for non-header kinds. */
export function disclaimerKey(kind: DisclaimerKind): string | null {
  switch (kind) {
    case 'legal_information_only':
    case 'medical_information_only':
    case 'benefits_information_only':
    case 'housing_information_only':
    case 'general_information':
      return `disclaimer.${kind}`;
    default:
      return null;
  }
}

/** Chip keys (S7 item 3). Banner-type warnings are handled by `resultBanners`. */
export const WARNING_CHIP_KEYS: Partial<Record<WarningCode, string>> = {
  low_quality_image: 'warning.low_quality_image',
  partial_pages: 'warning.partial_pages',
  page_edge_crop: 'warning.page_edge_crop',
  translation_partial: 'warning.translation_partial',
  blocked_partial: 'warning.blocked_partial',
  phrasing_lint_unavailable: 'warning.checks_unavailable',
  emergency_lexicon_unavailable: 'warning.checks_unavailable',
  contacts_stripped: 'warning.contacts_stripped',
};

/**
 * Chip keys for a result's warnings. `phrasing_lint_unavailable` shows only for a Tier 3 pack
 * (PRODUCT_SPEC §5.6 "chip (Tier 3 only)"): since CL-050(c) the server warns it for every
 * non-English target whose phrasing list is not reviewed yet (es, prs, ar… included), which would
 * put the chip on every result in the bundled languages. `emergency_lexicon_unavailable` (no
 * emergency list at all for the language) always shows — missing emergency detection is not a
 * notice to hide. Without `packTier` every mapped warning shows.
 */
export function warningChipKeys(warnings: readonly WarningCode[], opts: { packTier?: number } = {}): string[] {
  const out: string[] = [];
  for (const w of warnings) {
    if (w === 'phrasing_lint_unavailable' && opts.packTier !== undefined && opts.packTier < 3) continue;
    const key = WARNING_CHIP_KEYS[w];
    if (key && !out.includes(key)) out.push(key);
  }
  return out;
}

export interface BannerSpec {
  key: string;
  vars?: Record<string, string | number>;
  tone: 'info' | 'warning' | 'danger';
}

export interface BannerInputs {
  machineTranslated: boolean;
  uiTag: string;
}

/** S7 item 6 banners, in order. */
export function resultBanners(a: AnalysisResult, ui: BannerInputs): BannerSpec[] {
  const out: BannerSpec[] = [];
  const has = (w: WarningCode) => a.warnings.includes(w);
  if (has('unpaid_tier') || a.model_meta.data_use_tier === 'unpaid') out.push({ key: 'banner.unpaid_tier', tone: 'danger' });
  if (ui.machineTranslated) out.push({ key: 'banner.machine_translated', tone: 'warning' });
  if (a.translation_confidence === 'low') out.push({ key: 'banner.low_confidence_translation', tone: 'warning' });
  if (has('document_language_differs')) {
    out.push({
      key: 'banner.doc_language_differs',
      // "I explained it in {ui_language}": the language the result is written in, which the S5
      // output-language chip may have set apart from the UI language.
      vars: { doc_language: languageName(a.detected_language), ui_language: languageName(a.target_language || ui.uiTag) },
      tone: 'info',
    });
  }
  if (has('degraded_model') || a.model_meta.quality === 'degraded') out.push({ key: 'banner.degraded_model', tone: 'warning' });
  if (isSampleResult(a)) out.push({ key: 'banner.demo_sample', tone: 'info' });
  return out;
}

export const DEMO_AS_OF_NOTE_KEY = 'demo.as_of_note';

/**
 * The one fixed line under the urgency banner of a sample result that has dates (POLISH item 1):
 * the server computes a sample's dates, urgency and `days_until` as of one fixed day
 * (`apps/api/proxyhealth_api/demo/as_of.py` `DEMO_AS_OF`), and the app shows the server's
 * `days_until` as is — never recomputed from the device clock. Null for every other result.
 */
export function sampleAsOfNoteKey(a: AnalysisResult): string | null {
  return isSampleResult(a) && hasDates(a) ? DEMO_AS_OF_NOTE_KEY : null;
}

/** A sample paper (or any mock-mode result): `model_meta.demo` / the `demo_sample` warning. */
export function isSampleResult(a: Pick<AnalysisResult, 'warnings' | 'model_meta'>): boolean {
  return a.warnings.includes('demo_sample') || a.model_meta.demo;
}

function hasDates(a: AnalysisResult): boolean {
  return Boolean(a.urgency.nearest_date_iso) || a.demands.some((d) => Boolean(d.date?.value_iso));
}

export const FOOTER_KEYS = ['footer.ai_generated', 'footer.verify_with_sender'] as const;

/** A paper the server scored a possible or likely scam (an old stored result without the field
 *  counts as none). DOCUMENT_TAXONOMY §6.4: then nothing sends the reader to the paper's own
 *  contact — the sender is the scammer; the scam card says to check with the real office. */
export function isScamPaper(a: Pick<AnalysisResult, 'scam_risk'>): boolean {
  return a.scam_risk === 'likely' || a.scam_risk === 'possible';
}

/** S7 item 17 footer lines; a scam paper leaves out "Confirm dates and amounts with the sender". */
export function footerKeys(a: Pick<AnalysisResult, 'scam_risk'>): readonly (typeof FOOTER_KEYS)[number][] {
  return isScamPaper(a) ? FOOTER_KEYS.filter((k) => k !== 'footer.verify_with_sender') : FOOTER_KEYS;
}
