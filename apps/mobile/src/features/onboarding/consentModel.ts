// Consent view-model (D-02, PRODUCT_SPEC S2, COMPLIANCE_PRIVACY §4.2, free-ai-providers §5.2/§5.3).
// Pure: which badge, which lines (literally true per tier AND per AI provider), which buttons.
// `unknown` covers an unreachable `/v1/config` and tier `none`.
//
// Line choice (§5.2 table):
// - Gemini tiers are unchanged: `consent.line1` ("sent to Google's AI") on paid/unpaid/mixed and on
//   unknown; never in demo, where no AI service is contacted.
// - `local` (an open-weight model on the API host): `consent.line1.local` / `consent.line2.local`,
//   `{model}` from `ai_model_label`.
// - `attested` (a hosted vendor whose API terms say "no training"; development only):
//   `consent.line1.vendor` / `consent.line2.attested`, `{vendor}` from `ai_vendor_name`.
// - `unpaid` on `openai_compat`: `consent.line1.vendor` / `consent.line2.unpaid_vendor`.
// - The native "hide parts" line names Google (`consent.line4.masks`), so any non-Google provider
//   uses the vendor-neutral `consent.line4.masks_local` instead; web keeps `consent.line4.masks_web`.
// "I understand, continue" is shown on paid, demo, local and attested; hidden on unpaid/mixed.

import type { FeatureFlags, ServerConfig } from '@/api/types';
import type { ConsentRecord } from '@/storage/index';
import { type ConsentDecision, consentIsCurrent } from '@/storage/consent';
import type { UiTier } from '@/store/session';

export type ConsentTone = 'normal' | 'danger';

export interface ConsentLine {
  key: string;
  tone: ConsentTone;
  /** Pictogram id (not mirrored in RTL) and its alt-text key. */
  pictogram: 'cloud' | 'server' | 'phone' | 'masks' | null;
  altKey: string | null;
  /** Highlighted because it changed since the last consent (re-consent). */
  changed: boolean;
}

export type ViewTier = 'paid' | 'unpaid' | 'demo' | 'local' | 'attested' | 'unknown';

/** What the copy needs from `/v1/config` to name the AI (`{model}`, `{vendor}`). */
export type AiCopyInput = Partial<Pick<ServerConfig, 'provider' | 'ai_model_label' | 'ai_vendor_name'>>;

/** Placeholder values for `{model}` / `{vendor}` in the tier copy (§5.3). */
export interface ConsentVars {
  model: string;
  vendor: string;
  [name: string]: string;
}

export interface ConsentView {
  tier: ViewTier;
  badgeKey: string;
  lines: ConsentLine[];
  /** Pass to `t(line.key, vars)`: `{model}` / `{vendor}` from `/v1/config`. */
  vars: ConsentVars;
  /** "I understand, continue" is rendered (hidden on unpaid/mixed — nothing to consent to). */
  showContinue: boolean;
  /** Rendered but disabled (unknown tier, or the server left out the AI's name) with a hint. */
  continueDisabled: boolean;
  hintKey: string | null;
  /** The 72 pt action: continue, or "Try a sample paper first" on unpaid/mixed. */
  primary: 'continue' | 'sample';
  /** Title prefix `consent.changed` on re-consent. */
  changed: boolean;
}

export interface ConsentViewInput {
  tier: UiTier;
  platform: 'ios' | 'android' | 'web';
  features: Pick<FeatureFlags, 'hide_parts_server_masking'> | null;
  /** `/v1/config` provider + AI names; absent/null → the Gemini copy (unchanged behaviour). */
  ai?: AiCopyInput | null;
  /** The record the user accepted before (re-consent highlights what differs). */
  previous?: ConsentRecord | null;
}

export function viewTier(tier: UiTier): ViewTier {
  if (tier === 'paid') return 'paid';
  if (tier === 'unpaid' || tier === 'mixed') return 'unpaid';
  if (tier === 'demo') return 'demo';
  if (tier === 'local') return 'local';
  if (tier === 'attested') return 'attested';
  return 'unknown';
}

/** True when the copy must name a vendor other than Google (`AI_PROVIDER=openai_compat`). */
export function namesOtherAi(ai: AiCopyInput | null | undefined): boolean {
  return ai?.provider === 'openai_compat';
}

/**
 * The `ai_seen` value for a consent record: which AI the S2 copy named, so a vendor or model change
 * re-shows S2 (`consentIsCurrent`). Null for Gemini and the mock (their copy names no variable AI).
 */
export function aiSeenFor(ai: AiCopyInput | null | undefined): string | null {
  if (!namesOtherAi(ai)) return null;
  return `openai_compat|${ai?.ai_vendor_name ?? ''}|${ai?.ai_model_label ?? ''}`;
}

export function consentVars(ai: AiCopyInput | null | undefined): ConsentVars {
  return { model: ai?.ai_model_label?.trim() ?? '', vendor: ai?.ai_vendor_name?.trim() ?? '' };
}

/** The tier- and provider-specific keys shared by S2 and the privacy notice (§5.2 table). */
export interface TierCopy {
  /** S2 line 1 (how the photo is read); null in demo and for an unknown non-Google provider. */
  line1: string | null;
  line2: string;
  /** Native "hide parts" line (only when `features.hide_parts_server_masking`). */
  masksNative: string;
  /** Privacy notice item 1 (COMPLIANCE_PRIVACY §4.5); null where S2 has no line 1. */
  noticeSent: string | null;
  /** Extra privacy-notice lines after item 1 (e.g. `privacy.notice.model.local`). */
  noticeExtra: string[];
  /** Placeholders the copy needs; missing values block Continue (the sentence would be broken). */
  needs: ('model' | 'vendor')[];
}

export function tierCopy(v: ViewTier, ai: AiCopyInput | null | undefined): TierCopy {
  const other = namesOtherAi(ai);
  switch (v) {
    case 'local':
      return {
        line1: 'consent.line1.local',
        line2: 'consent.line2.local',
        masksNative: 'consent.line4.masks_local',
        noticeSent: 'privacy.notice.sent.local',
        noticeExtra: ['privacy.notice.model.local'],
        needs: ['model'],
      };
    case 'attested':
      return {
        line1: 'consent.line1.vendor',
        line2: 'consent.line2.attested',
        masksNative: 'consent.line4.masks_local',
        noticeSent: 'consent.line1.vendor',
        noticeExtra: [],
        needs: ['vendor'],
      };
    case 'unpaid':
      return other
        ? {
            line1: 'consent.line1.vendor',
            line2: 'consent.line2.unpaid_vendor',
            masksNative: 'consent.line4.masks_local',
            noticeSent: 'consent.line1.vendor',
            noticeExtra: [],
            needs: ['vendor'],
          }
        : googleCopy('consent.line2.unpaid');
    case 'demo':
      return { ...googleCopy('consent.line2.demo'), line1: null, noticeSent: null };
    case 'unknown':
      // Config unreachable. A cached config naming another AI: say nothing about Google.
      return other
        ? {
            line1: null,
            line2: 'consent.line2.unknown',
            masksNative: 'consent.line4.masks_local',
            noticeSent: null,
            noticeExtra: [],
            needs: [],
          }
        : googleCopy('consent.line2.unknown');
    case 'paid':
    default:
      return googleCopy('consent.line2.paid');
  }
}

function googleCopy(line2: string): TierCopy {
  return {
    line1: 'consent.line1',
    line2,
    masksNative: 'consent.line4.masks',
    noticeSent: 'privacy.notice.sent',
    noticeExtra: [],
    needs: [],
  };
}

export function consentView({ tier, platform, features, ai, previous }: ConsentViewInput): ConsentView {
  const v = viewTier(tier);
  const copy = tierCopy(v, ai);
  const vars = consentVars(ai);
  const missingName = copy.needs.some((name) => vars[name].length === 0);
  const changed = Boolean(previous);
  const tierChanged = Boolean(previous && viewTier(previous.tier_seen) !== v);
  const aiChanged = Boolean(previous && v !== 'unknown' && (previous.ai_seen ?? null) !== aiSeenFor(ai));
  const lines: ConsentLine[] = [];
  if (copy.line1) {
    const local = v === 'local';
    lines.push({
      key: copy.line1,
      tone: 'normal',
      // The local model runs on our server: no cloud pictogram (its alt text would be false).
      pictogram: local ? 'server' : 'cloud',
      altKey: local ? 'consent.pictogram2_alt' : 'consent.pictogram1_alt',
      changed: aiChanged,
    });
  }
  lines.push({
    key: copy.line2,
    tone: v === 'unpaid' ? 'danger' : 'normal',
    pictogram: 'server',
    altKey: 'consent.pictogram2_alt',
    changed: tierChanged,
  });
  lines.push({
    key: platform === 'web' ? 'consent.line3.web' : 'consent.line3',
    tone: 'normal',
    pictogram: 'phone',
    altKey: 'consent.pictogram3_alt',
    changed: false,
  });
  if (platform === 'web') {
    lines.push({ key: 'consent.line4.masks_web', tone: 'normal', pictogram: null, altKey: null, changed: false });
  } else if (features?.hide_parts_server_masking) {
    lines.push({ key: copy.masksNative, tone: 'normal', pictogram: null, altKey: null, changed: false });
  }
  const showContinue = v !== 'unpaid';
  const continueDisabled = v === 'unknown' || (showContinue && missingName);
  return {
    tier: v,
    badgeKey: `consent.badge.${v}`,
    lines,
    vars,
    showContinue,
    continueDisabled,
    hintKey: continueDisabled ? 'consent.unknown_hint' : null,
    primary: v === 'unpaid' ? 'sample' : 'continue',
    changed,
  };
}

export type StartRoute = '/onboarding/language' | '/onboarding/consent' | '/(tabs)';

export interface StartInput {
  languageDecided: boolean;
  decision: ConsentDecision;
  record: ConsentRecord | null;
  serverConsentVersion: string | null;
  tier: UiTier;
  /** `aiSeenFor(config)` when the config is known; undefined skips the AI-change check. */
  aiNow?: string | null;
}

/**
 * S0 redirect (PRODUCT_SPEC S0): no language → S1; no consent decision → S2; an accepted record
 * that no longer matches the server's consent version, tier or named AI → S2 (re-consent); else the
 * tabs. "Not now" and "withdrawn" go to the tabs (scan disabled there).
 */
export function startRoute(input: StartInput): StartRoute {
  if (!input.languageDecided) return '/onboarding/language';
  if (input.decision === 'none') return '/onboarding/consent';
  if (input.decision === 'accepted') {
    const tierNow = input.tier === 'unknown' || input.tier === 'none' ? null : input.tier;
    const aiNow = tierNow ? input.aiNow : undefined;
    if (!consentIsCurrent(input.record, input.serverConsentVersion, tierNow, aiNow)) return '/onboarding/consent';
  }
  return '/(tabs)';
}
