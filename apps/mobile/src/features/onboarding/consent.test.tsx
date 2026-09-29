// S2 consent (D-02, BUILD_PLAN §5.5 step 4): badge + copy per tier incl. `unknown`, the "Not now"
// path, the stored record shape, and the S0 redirect rules.

import { fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import { resetServerConfigSession } from '@/api/config';
import type { ServerConfig } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { consentStore } from '@/storage/consent';
import { kv, KV_KEYS } from '@/storage/kv';
import { useSession } from '@/store/session';

import { consentView, startRoute } from './consentModel';
import { ConsentScreen } from './ConsentScreen';
import { resetConsentState, useConsentDecision } from './consentState';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const keys = (tier: Parameters<typeof consentView>[0]['tier'], platform: 'ios' | 'web' = 'ios', masking = true) =>
  consentView({ tier, platform, features: { hide_parts_server_masking: masking } }).lines.map((l) => l.key);

describe('consentView per tier', () => {
  it('paid: line 1 + paid line 2 + line 3 + native masks line; Continue enabled', () => {
    const v = consentView({ tier: 'paid', platform: 'android', features: { hide_parts_server_masking: true } });
    expect(v.badgeKey).toBe('consent.badge.paid');
    expect(keys('paid')).toEqual(['consent.line1', 'consent.line2.paid', 'consent.line3', 'consent.line4.masks']);
    expect(v.showContinue && !v.continueDisabled && v.primary === 'continue').toBe(true);
  });

  it('unpaid and mixed: red line 2, Continue hidden, sample is primary', () => {
    for (const tier of ['unpaid', 'mixed'] as const) {
      const v = consentView({ tier, platform: 'ios', features: null });
      expect(v.badgeKey).toBe('consent.badge.unpaid');
      expect(v.lines.find((l) => l.key === 'consent.line2.unpaid')?.tone).toBe('danger');
      expect(v.showContinue).toBe(false);
      expect(v.primary).toBe('sample');
    }
  });

  it('demo: no "sent to Google" line (nothing reaches an AI service)', () => {
    expect(keys('demo')).toEqual(['consent.line2.demo', 'consent.line3', 'consent.line4.masks']);
    expect(consentView({ tier: 'demo', platform: 'ios', features: null }).badgeKey).toBe('consent.badge.demo');
  });

  it('unknown and none: Continue disabled with the unknown hint', () => {
    for (const tier of ['unknown', 'none'] as const) {
      const v = consentView({ tier, platform: 'ios', features: null });
      expect(v.badgeKey).toBe('consent.badge.unknown');
      expect(v.continueDisabled).toBe(true);
      expect(v.hintKey).toBe('consent.unknown_hint');
      expect(v.lines.map((l) => l.key)).toContain('consent.line2.unknown');
    }
  });

  it('web: line 3 and the masks line use the browser wording', () => {
    expect(keys('paid', 'web', false)).toEqual(['consent.line1', 'consent.line2.paid', 'consent.line3.web', 'consent.line4.masks_web']);
    expect(keys('paid', 'ios', false)).not.toContain('consent.line4.masks');
  });

  it('re-consent highlights line 2 when the tier changed', () => {
    const v = consentView({
      tier: 'paid',
      platform: 'ios',
      features: null,
      previous: { consent_version: '2026-09-01', accepted_at: 'x', tier_seen: 'demo', platform: 'ios' },
    });
    expect(v.changed).toBe(true);
    expect(v.lines.find((l) => l.key === 'consent.line2.paid')?.changed).toBe(true);
  });
});

describe('startRoute (S0)', () => {
  const record = { consent_version: '2026-09-24', accepted_at: 'x', tier_seen: 'paid' as const, platform: 'ios' as const };
  const base = { languageDecided: true, decision: 'accepted' as const, record, serverConsentVersion: '2026-09-24', tier: 'paid' as const };
  it('routes language → consent → tabs', () => {
    expect(startRoute({ ...base, languageDecided: false })).toBe('/onboarding/language');
    expect(startRoute({ ...base, decision: 'none', record: null })).toBe('/onboarding/consent');
    expect(startRoute(base)).toBe('/(tabs)');
    expect(startRoute({ ...base, decision: 'not_now', record: null })).toBe('/(tabs)');
  });
  it('re-shows consent on a new consent version or tier, not while offline', () => {
    expect(startRoute({ ...base, serverConsentVersion: '2026-10-01' })).toBe('/onboarding/consent');
    expect(startRoute({ ...base, tier: 'demo' })).toBe('/onboarding/consent');
    expect(startRoute({ ...base, tier: 'unknown', serverConsentVersion: null })).toBe('/(tabs)');
  });
});

function configClient(config: ServerConfig | null): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({} as ApiClient, {
    get: (_t, prop) => {
      if (prop === 'getConfig') return () => (config ? Promise.resolve(config) : fail());
      if (prop === 'baseUrl') return 'http://127.0.0.1:8026';
      return fail;
    },
  });
}

function demoConfig(): ServerConfig {
  return {
    api_version: '0.1.0',
    contract_version: 1,
    provider: 'mock',
    data_use_tier: 'demo',
    models: { fast: 'gemini-3.5-flash-lite', pro: 'gemini-3.8-flash', pro_degraded_thinking: 'medium' },
    features: {
      real_documents_allowed: false,
      demo_samples: true,
      dynamic_language_packs: true,
      troubleshoot: true,
      chat: true,
      quicksheet_pdf: true,
      degraded_fallback: true,
      hide_parts_server_masking: true,
    },
    limits: {} as ServerConfig['limits'],
    consent_version: '2026-09-24',
    privacy_policy_url: 'https://proxyhealth.expo.app/privacy',
    base_pack_version: 'base',
    languages: [],
    taxonomy_version: 't',
    resource_db_version: 'r',
    rules_version: 'rv',
    key_slots: { total: 0, healthy: 0, cooling: 0, rpd_exhausted: 0, disabled: 0 },
    region_notice: 'us_only',
    server_time: '2026-09-27T00:00:00Z',
  } as ServerConfig;
}

describe('<ConsentScreen>', () => {
  beforeEach(async () => {
    await kv.clearAll();
    resetConsentState();
    resetServerConfigSession();
    useSession.getState().reset();
  });

  it('mock server → "Sample mode" badge; Continue stores the record shape', async () => {
    const navigate = jest.fn();
    const { findByTestId, getByText, getByTestId } = await render(
      <AppProviders client={configClient(demoConfig())} staticMetrics>
        <ConsentScreen navigate={navigate} />
      </AppProviders>,
    );
    expect(await findByTestId('tier-badge-demo')).toBeTruthy();
    expect(getByText('This app is for adults 18 and older.')).toBeTruthy();
    expect(getByTestId('consent-line-consent.line2.demo')).toBeTruthy();
    fireEvent.press(getByTestId('consent-continue'));
    await new Promise((r) => setTimeout(r, 10));
    const record = await consentStore.get();
    expect(record).toEqual({
      consent_version: '2026-09-24',
      accepted_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
      tier_seen: 'demo',
      platform: 'ios',
    });
    expect(useSession.getState().consent?.consent_version).toBe('2026-09-24');
    expect(navigate).toHaveBeenCalledWith('/(tabs)');
  });

  it('unreachable server → "Cannot confirm"; Not now stores no record and goes to the tabs', async () => {
    const navigate = jest.fn();
    const { findByTestId, getByText, getByTestId } = await render(
      <AppProviders client={configClient(null)} staticMetrics>
        <ConsentScreen navigate={navigate} />
      </AppProviders>,
    );
    expect(await findByTestId('tier-badge-unknown')).toBeTruthy();
    expect(getByText('Come back when you have internet to confirm this.')).toBeTruthy();
    fireEvent.press(getByTestId('consent-not-now'));
    await new Promise((r) => setTimeout(r, 10));
    expect(await consentStore.get()).toBeNull();
    expect(await kv.getJSON<{ decision: string }>(KV_KEYS.consentDecision)).toMatchObject({ decision: 'not_now' });
    expect(useConsentDecision.getState().decision).toBe('not_now');
    expect(navigate).toHaveBeenCalledWith('/(tabs)');
  });
});
