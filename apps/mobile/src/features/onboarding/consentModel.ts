// Consent view-model (D-02, PRODUCT_SPEC S2, COMPLIANCE_PRIVACY §4.2). Pure: which badge, which
// lines (literally true per tier), which buttons. `unknown` covers an unreachable `/v1/config` and
// tier `none`. Line 1 ("sent to Google's AI") is shown for paid/unpaid/mixed/unknown — never in
// demo, where no AI service is contacted.

import type { FeatureFlags } from '@/api/types';
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

export interface ConsentView {
  tier: 'paid' | 'unpaid' | 'demo' | 'unknown';
  badgeKey: string;
  lines: ConsentLine[];
  /** "I understand, continue" is rendered (hidden on unpaid/mixed — nothing to consent to). */
  showContinue: boolean;
  /** Rendered but disabled (unknown tier) with `consent.unknown_hint`. */
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
  /** The record the user accepted before (re-consent highlights what differs). */
  previous?: ConsentRecord | null;
}

export function viewTier(tier: UiTier): ConsentView['tier'] {
  if (tier === 'paid') return 'paid';
  if (tier === 'unpaid' || tier === 'mixed') return 'unpaid';
  if (tier === 'demo') return 'demo';
  return 'unknown';
}

export function consentView({ tier, platform, features, previous }: ConsentViewInput): ConsentView {
  const v = viewTier(tier);
  const changed = Boolean(previous);
  const tierChanged = Boolean(previous && viewTier(previous.tier_seen) !== v);
  const lines: ConsentLine[] = [];
  if (v !== 'demo') {
    lines.push({ key: 'consent.line1', tone: 'normal', pictogram: 'cloud', altKey: 'consent.pictogram1_alt', changed: false });
  }
  lines.push({
    key: `consent.line2.${v}`,
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
    lines.push({ key: 'consent.line4.masks', tone: 'normal', pictogram: null, altKey: null, changed: false });
  }
  return {
    tier: v,
    badgeKey: `consent.badge.${v}`,
    lines,
    showContinue: v !== 'unpaid',
    continueDisabled: v === 'unknown',
    hintKey: v === 'unknown' ? 'consent.unknown_hint' : null,
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
}

/**
 * S0 redirect (PRODUCT_SPEC S0): no language → S1; no consent decision → S2; an accepted record
 * that no longer matches the server's consent version or tier → S2 (re-consent); else the tabs.
 * "Not now" and "withdrawn" go to the tabs (scan disabled there).
 */
export function startRoute(input: StartInput): StartRoute {
  if (!input.languageDecided) return '/onboarding/language';
  if (input.decision === 'none') return '/onboarding/consent';
  if (input.decision === 'accepted') {
    const tierNow = input.tier === 'unknown' || input.tier === 'none' ? null : input.tier;
    if (!consentIsCurrent(input.record, input.serverConsentVersion, tierNow)) return '/onboarding/consent';
  }
  return '/(tabs)';
}
