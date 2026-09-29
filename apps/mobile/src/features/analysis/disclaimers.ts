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

export function warningChipKeys(warnings: readonly WarningCode[]): string[] {
  const out: string[] = [];
  for (const w of warnings) {
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
      vars: { doc_language: languageName(a.detected_language), ui_language: languageName(ui.uiTag) },
      tone: 'info',
    });
  }
  if (has('degraded_model') || a.model_meta.quality === 'degraded') out.push({ key: 'banner.degraded_model', tone: 'warning' });
  if (has('demo_sample') || a.model_meta.demo) out.push({ key: 'banner.demo_sample', tone: 'info' });
  return out;
}

export const FOOTER_KEYS = ['footer.ai_generated', 'footer.verify_with_sender'] as const;
