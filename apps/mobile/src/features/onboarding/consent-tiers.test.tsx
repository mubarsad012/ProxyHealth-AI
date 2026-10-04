// Phase 3 consent copy per data-use tier and AI provider (free-ai-providers §5.2 table, §5.3
// sentences): S2 lines, badge, banner, privacy notice, Continue visibility, `{model}` / `{vendor}`
// from `/v1/config`, re-consent when the named AI changes, and the 18+ speaker button.

import { fireEvent, render, within } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import { resetServerConfigSession } from '@/api/config';
import type { ServerConfig } from '@/api/types';
import { TierBanner, tierBannerKind } from '@/design/components/Banner';
import { AppProviders } from '@/design/components/Providers';
import { badgeTier, TierBadge, tierBadgeKey } from '@/design/components/TierBadge';
import { BASE_STRINGS } from '@/i18n/store';
import { buildConsentRecord, consentIsCurrent, consentStore } from '@/storage/consent';
import { kv } from '@/storage/kv';
import { realUploadsAllowed, useSession } from '@/store/session';

import { aiSeenFor, consentView, startRoute, tierCopy } from './consentModel';
import { ConsentScreen } from './ConsentScreen';
import { PrivacyNoticeContent, privacyNoticeKeys } from './PrivacyNotice';
import { resetConsentState } from './consentState';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('expo-notifications', () => ({ cancelAllScheduledNotificationsAsync: jest.fn(async () => undefined) }));

/** §5.3 English copy, verbatim. en.json (COPY, stage 3) wins once it has these keys. */
const PHASE3_EN: Record<string, string> = {
  'consent.badge.local': 'Test build — AI on our server',
  'consent.line1.local':
    'Your photo is read by {model}, an AI program that runs on our server. Our server does not keep it.',
  'consent.line2.local':
    "No other company's AI sees your paper. This is a test build. Check every answer against your paper.",
  'consent.line4.masks_local': 'Parts you hide are blacked out on our server before the AI reads the paper.',
  'privacy.notice.sent.local':
    'When you read a paper, the photo goes to our server. An AI program on our server reads it. Our server does not keep it.',
  'privacy.notice.model.local': '{model} is an open AI model. The company that made it does not get your paper.',
  'banner.local_tier': 'Test build. The AI runs on our server.',
  'consent.badge.attested': 'Test build — outside AI',
  'consent.line1.vendor': "Your photo is sent to {vendor}'s AI to be read. Our server does not keep it.",
  'consent.line2.attested':
    '{vendor} says it will not use your paper to train its AI. It may still keep a copy. This is a test build. Send only your own papers.',
  'banner.attested_tier': 'Test build with an outside AI. Send only your own papers.',
  'consent.line2.unpaid_vendor':
    'This test build uses a free AI service. {vendor} may read and use what is sent. Do not send real papers. Sample papers only.',
};

// The providers reload the bundled pack on mount, so the copy is added to the English base the
// lookup falls back to — only where en.json does not have the key yet.
for (const [key, value] of Object.entries(PHASE3_EN)) {
  if (typeof BASE_STRINGS[key] !== 'string') BASE_STRINGS[key] = value;
}

const LOCAL_AI = { provider: 'openai_compat', ai_model_label: 'Qwen', ai_vendor_name: null } as const;
const ATTESTED_AI = { provider: 'openai_compat', ai_model_label: 'Llama', ai_vendor_name: 'Groq' } as const;
const GEMINI_AI = { provider: 'gemini', ai_model_label: 'Gemini', ai_vendor_name: 'Google' } as const;

const lineKeys = (v: ReturnType<typeof consentView>) => v.lines.map((l) => l.key);
const masking = { hide_parts_server_masking: true };

describe('consentView: local tier (§5.2)', () => {
  const v = consentView({ tier: 'local', platform: 'android', features: masking, ai: LOCAL_AI });
  it('local badge, local lines 1/2, vendor-neutral masks line, Continue shown and enabled', () => {
    expect(v.badgeKey).toBe('consent.badge.local');
    expect(lineKeys(v)).toEqual(['consent.line1.local', 'consent.line2.local', 'consent.line3', 'consent.line4.masks_local']);
    expect(v.showContinue && !v.continueDisabled && v.primary === 'continue').toBe(true);
    expect(v.hintKey).toBeNull();
    expect(v.vars.model).toBe('Qwen');
  });
  it('no cloud pictogram for a model that runs on our server', () => {
    expect(v.lines[0]).toMatchObject({ pictogram: 'server', altKey: 'consent.pictogram2_alt' });
    expect(v.lines.some((l) => l.pictogram === 'cloud')).toBe(false);
  });
  it('web keeps the on-device masks line', () => {
    const web = consentView({ tier: 'local', platform: 'web', features: masking, ai: LOCAL_AI });
    expect(lineKeys(web)).toEqual(['consent.line1.local', 'consent.line2.local', 'consent.line3.web', 'consent.line4.masks_web']);
  });
  it('a missing model name blocks Continue (the sentence would show "{model}")', () => {
    const broken = consentView({ tier: 'local', platform: 'ios', features: null, ai: { provider: 'openai_compat' } });
    expect(broken.showContinue).toBe(true);
    expect(broken.continueDisabled).toBe(true);
    expect(broken.hintKey).toBe('consent.unknown_hint');
  });
});

describe('consentView: attested tier (§5.2)', () => {
  it('attested badge, vendor line 1, attested line 2, Continue shown', () => {
    const v = consentView({ tier: 'attested', platform: 'ios', features: masking, ai: ATTESTED_AI });
    expect(v.badgeKey).toBe('consent.badge.attested');
    expect(lineKeys(v)).toEqual(['consent.line1.vendor', 'consent.line2.attested', 'consent.line3', 'consent.line4.masks_local']);
    expect(v.showContinue && !v.continueDisabled).toBe(true);
    expect(v.vars.vendor).toBe('Groq');
    expect(lineKeys(v)).not.toContain('consent.line1');
  });
  it('a missing vendor name blocks Continue', () => {
    const v = consentView({ tier: 'attested', platform: 'ios', features: null, ai: { provider: 'openai_compat', ai_model_label: 'X' } });
    expect(v.continueDisabled).toBe(true);
  });
});

describe('consentView: unpaid with another vendor, and Gemini unchanged', () => {
  it('unpaid on openai_compat: vendor lines, red line 2, Continue hidden', () => {
    for (const tier of ['unpaid', 'mixed'] as const) {
      const v = consentView({ tier, platform: 'android', features: masking, ai: ATTESTED_AI });
      expect(v.badgeKey).toBe('consent.badge.unpaid');
      expect(lineKeys(v)).toEqual(['consent.line1.vendor', 'consent.line2.unpaid_vendor', 'consent.line3', 'consent.line4.masks_local']);
      expect(v.lines[1].tone).toBe('danger');
      expect(v.showContinue).toBe(false);
      expect(v.primary).toBe('sample');
    }
  });
  it('Gemini (or no provider known) keeps the Google copy on every tier', () => {
    for (const ai of [GEMINI_AI, null, undefined]) {
      expect(lineKeys(consentView({ tier: 'paid', platform: 'ios', features: masking, ai }))).toEqual([
        'consent.line1',
        'consent.line2.paid',
        'consent.line3',
        'consent.line4.masks',
      ]);
      expect(lineKeys(consentView({ tier: 'unpaid', platform: 'ios', features: null, ai })).slice(0, 2)).toEqual([
        'consent.line1',
        'consent.line2.unpaid',
      ]);
      expect(lineKeys(consentView({ tier: 'unknown', platform: 'ios', features: null, ai })).slice(0, 2)).toEqual([
        'consent.line1',
        'consent.line2.unknown',
      ]);
    }
  });
  it('unknown with a cached config naming another AI says nothing about Google', () => {
    const v = consentView({ tier: 'unknown', platform: 'ios', features: masking, ai: LOCAL_AI });
    expect(lineKeys(v)).toEqual(['consent.line2.unknown', 'consent.line3', 'consent.line4.masks_local']);
    expect(v.continueDisabled).toBe(true);
  });
});

describe('privacy notice per tier (COMPLIANCE_PRIVACY §4.5 + §5.3)', () => {
  it('local: sent.local, model.local, line2.local; no Google sentence', () => {
    const keys = privacyNoticeKeys('local', 'ios', LOCAL_AI);
    expect(keys.slice(0, 3)).toEqual(['privacy.notice.sent.local', 'privacy.notice.model.local', 'consent.line2.local']);
    expect(keys).not.toContain('privacy.notice.sent');
  });
  it('attested and unpaid-vendor: the vendor line replaces "goes to Google\'s AI"', () => {
    expect(privacyNoticeKeys('attested', 'web', ATTESTED_AI).slice(0, 2)).toEqual(['consent.line1.vendor', 'consent.line2.attested']);
    expect(privacyNoticeKeys('unpaid', 'ios', ATTESTED_AI).slice(0, 2)).toEqual(['consent.line1.vendor', 'consent.line2.unpaid_vendor']);
    expect(privacyNoticeKeys('attested', 'web', ATTESTED_AI)).not.toContain('privacy.notice.sent');
  });
  it('Gemini tiers unchanged', () => {
    expect(privacyNoticeKeys('paid', 'ios', GEMINI_AI).slice(0, 2)).toEqual(['privacy.notice.sent', 'consent.line2.paid']);
    expect(tierCopy('paid', GEMINI_AI).noticeExtra).toEqual([]);
  });
});

describe('badges and banners per tier', () => {
  it('badge keys', () => {
    expect(tierBadgeKey('local')).toBe('consent.badge.local');
    expect(tierBadgeKey('attested')).toBe('consent.badge.attested');
    expect(badgeTier('mixed')).toBe('unpaid');
    expect(badgeTier('none')).toBe('unknown');
  });
  it('banner kinds', () => {
    expect(tierBannerKind('local')).toBe('local');
    expect(tierBannerKind('attested')).toBe('attested');
    expect(tierBannerKind('unpaid')).toBe('unpaid');
    expect(tierBannerKind('mixed')).toBe('unpaid');
    for (const tier of ['paid', 'demo', 'none', 'unknown'] as const) expect(tierBannerKind(tier)).toBeNull();
  });
});

describe('real uploads on the new tiers', () => {
  const consent = buildConsentRecord('2026-10-01', 'local');
  it('local and attested allow real papers when the server does', () => {
    for (const tier of ['local', 'attested'] as const) {
      const base = { ...useSession.getState(), consent, tier };
      expect(realUploadsAllowed({ ...base, serverConfig: { features: { real_documents_allowed: true } } as ServerConfig })).toBe(true);
      expect(realUploadsAllowed({ ...base, serverConfig: { features: { real_documents_allowed: false } } as ServerConfig })).toBe(false);
    }
  });
});

describe('re-consent when the named AI changes', () => {
  it('ai_seen is written only for openai_compat', () => {
    expect(aiSeenFor(GEMINI_AI)).toBeNull();
    expect(aiSeenFor(null)).toBeNull();
    expect(aiSeenFor(ATTESTED_AI)).toBe('openai_compat|Groq|Llama');
    expect(buildConsentRecord('v', 'paid', null)).not.toHaveProperty('ai_seen');
    expect(buildConsentRecord('v', 'attested', 'openai_compat|Groq|Llama').ai_seen).toBe('openai_compat|Groq|Llama');
  });
  it('a different vendor on the same tier re-shows S2; the same one does not', () => {
    const record = buildConsentRecord('2026-10-04', 'attested', aiSeenFor(ATTESTED_AI));
    const base = { languageDecided: true, decision: 'accepted' as const, record, serverConsentVersion: '2026-10-04', tier: 'attested' as const };
    expect(startRoute({ ...base, aiNow: aiSeenFor(ATTESTED_AI) })).toBe('/(tabs)');
    expect(startRoute({ ...base, aiNow: aiSeenFor({ ...ATTESTED_AI, ai_vendor_name: 'Alibaba Cloud' }) })).toBe('/onboarding/consent');
    // Offline (unknown tier): no re-consent from a stale comparison.
    expect(startRoute({ ...base, tier: 'unknown', serverConsentVersion: null, aiNow: 'x' })).toBe('/(tabs)');
  });
  it('old Gemini records (no ai_seen) stay current on Gemini', () => {
    const record = buildConsentRecord('2026-10-01', 'paid');
    expect(consentIsCurrent(record, '2026-10-01', 'paid', null)).toBe(true);
    expect(consentIsCurrent(record, '2026-10-01', 'paid')).toBe(true);
  });
  it('line 1 is highlighted when the AI changed', () => {
    const previous = buildConsentRecord('2026-10-01', 'attested', 'openai_compat|Groq|Llama');
    const v = consentView({ tier: 'attested', platform: 'ios', features: null, ai: { ...ATTESTED_AI, ai_vendor_name: 'Cerebras' }, previous });
    expect(v.lines[0]).toMatchObject({ key: 'consent.line1.vendor', changed: true });
    expect(v.lines[1].changed).toBe(false);
  });
});

// --- rendered screen --------------------------------------------------------------------------

function configClient(config: ServerConfig | null): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({} as ApiClient, {
    get: (_t, prop) => {
      if (prop === 'getConfig') return () => (config ? Promise.resolve(config) : fail());
      if (prop === 'baseUrl') return 'http://127.0.0.1:8053';
      return fail;
    },
  });
}

function compatConfig(tier: 'local' | 'attested' | 'unpaid', ai: { ai_model_label: string | null; ai_vendor_name: string | null }): ServerConfig {
  return {
    api_version: '0.1.0',
    contract_version: 1,
    provider: 'openai_compat',
    data_use_tier: tier,
    ...ai,
    models: { fast: 'qwen3.5:4b', pro: 'qwen3.5:4b', pro_degraded_thinking: 'medium' },
    features: {
      real_documents_allowed: tier !== 'unpaid',
      demo_samples: true,
      dynamic_language_packs: true,
      troubleshoot: true,
      chat: tier !== 'unpaid',
      quicksheet_pdf: true,
      degraded_fallback: false,
      hide_parts_server_masking: true,
    },
    limits: {} as ServerConfig['limits'],
    consent_version: '2026-10-04',
    privacy_policy_url: 'https://proxyhealth.expo.app/privacy',
    base_pack_version: 'base',
    languages: [],
    taxonomy_version: 't',
    resource_db_version: 'r',
    rules_version: 'rv',
    key_slots: { total: 1, healthy: 1, cooling: 0, rpd_exhausted: 0, disabled: 0 },
    region_notice: 'us_only',
    server_time: '2026-10-04T00:00:00Z',
  } as ServerConfig;
}

describe('<ConsentScreen> on the new tiers', () => {
  beforeEach(async () => {
    await kv.clearAll();
    resetConsentState();
    resetServerConfigSession();
    useSession.getState().reset();
  });

  it('local: badge + sentences with {model}; Continue stores tier_seen local and ai_seen', async () => {
    const navigate = jest.fn();
    const { findByTestId, getByText, getByTestId, queryByText } = await render(
      <AppProviders client={configClient(compatConfig('local', { ai_model_label: 'Qwen', ai_vendor_name: null }))} staticMetrics>
        <ConsentScreen navigate={navigate} />
      </AppProviders>,
    );
    expect(await findByTestId('tier-badge-local')).toBeTruthy();
    expect(getByText('Test build — AI on our server')).toBeTruthy();
    expect(getByText('Your photo is read by Qwen, an AI program that runs on our server. Our server does not keep it.')).toBeTruthy();
    expect(getByTestId('consent-line-consent.line2.local')).toBeTruthy();
    expect(queryByText(/Google/)).toBeNull();
    fireEvent.press(getByTestId('consent-continue'));
    await new Promise((r) => setTimeout(r, 10));
    expect(await consentStore.get()).toMatchObject({ tier_seen: 'local', ai_seen: 'openai_compat||Qwen' });
    expect(navigate).toHaveBeenCalledWith('/(tabs)');
  });

  it('attested: {vendor} in lines 1 and 2; Continue shown', async () => {
    const { findByTestId, getByText, getByTestId } = await render(
      <AppProviders client={configClient(compatConfig('attested', { ai_model_label: 'Llama', ai_vendor_name: 'Groq' }))} staticMetrics>
        <ConsentScreen navigate={jest.fn()} />
      </AppProviders>,
    );
    expect(await findByTestId('tier-badge-attested')).toBeTruthy();
    expect(getByText("Your photo is sent to Groq's AI to be read. Our server does not keep it.")).toBeTruthy();
    expect(getByText(/^Groq says it will not use your paper to train its AI\./)).toBeTruthy();
    expect(getByTestId('consent-continue').props.accessibilityState).toMatchObject({ disabled: false });
  });

  it('unpaid on another vendor: Continue hidden, red vendor line', async () => {
    const { findByTestId, getByText, queryByTestId } = await render(
      <AppProviders client={configClient(compatConfig('unpaid', { ai_model_label: 'GLM', ai_vendor_name: 'Z.ai' }))} staticMetrics>
        <ConsentScreen navigate={jest.fn()} />
      </AppProviders>,
    );
    expect(await findByTestId('tier-badge-unpaid')).toBeTruthy();
    expect(getByText(/Z\.ai may read and use what is sent\./)).toBeTruthy();
    expect(queryByTestId('consent-continue')).toBeNull();
  });

  it('the 18+ line has its own speaker button', async () => {
    const { findByTestId } = await render(
      <AppProviders client={configClient(compatConfig('local', { ai_model_label: 'Qwen', ai_vendor_name: null }))} staticMetrics>
        <ConsentScreen navigate={jest.fn()} />
      </AppProviders>,
    );
    await findByTestId('tier-badge-local');
    const row = await findByTestId('consent-adults-only');
    const speaker = within(row).getByLabelText('Read aloud');
    expect(speaker.props.role).toBe('button');
  });
});

describe('rendered badge, banner and notice', () => {
  beforeEach(() => {
    useSession.getState().reset();
  });

  it('TierBadge and TierBanner show the local / attested words', async () => {
    const { getByTestId, getByText } = await render(
      <AppProviders client={configClient(null)} staticMetrics>
        <TierBadge tier="attested" />
        <TierBanner tier="local" />
        <TierBanner tier="attested" />
        <TierBanner tier="paid" />
      </AppProviders>,
    );
    expect(getByTestId('tier-badge-attested')).toBeTruthy();
    expect(getByText('Test build — outside AI')).toBeTruthy();
    expect(getByTestId('banner-local').props.role).toBe('status');
    expect(getByText('Test build. The AI runs on our server.')).toBeTruthy();
    expect(getByTestId('banner-attested').props.role).toBe('alert');
    expect(getByText('Test build with an outside AI. Send only your own papers.')).toBeTruthy();
  });

  it('privacy notice on local names the model from /v1/config', async () => {
    useSession.getState().setServerConfig(compatConfig('local', { ai_model_label: 'Qwen', ai_vendor_name: null }));
    const { getByText, queryByTestId } = await render(
      <AppProviders client={configClient(null)} staticMetrics>
        <PrivacyNoticeContent />
      </AppProviders>,
    );
    expect(getByText('Qwen is an open AI model. The company that made it does not get your paper.')).toBeTruthy();
    expect(queryByTestId('privacy-notice-privacy.notice.sent')).toBeNull();
    expect(queryByTestId('privacy-notice-privacy.notice.sent.local')).toBeTruthy();
  });
});
