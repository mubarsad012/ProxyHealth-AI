// S2 consent (D-02, BUILD_PLAN §5.5 step 4): badge + copy per tier incl. `unknown`, the "Not now"
// path, the stored record shape, and the S0 redirect rules.

import { fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import { installIdForRequests, resetServerConfigSession } from '@/api/config';
import type { ServerConfig } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { consentStore } from '@/storage/consent';
import { kv, KV_KEYS } from '@/storage/kv';
import { wipeEverything } from '@/storage/wipe';
import { useSession } from '@/store/session';

import { consentView, startRoute } from './consentModel';
import { ConsentScreen } from './ConsentScreen';
import { privacyNoticeKeys } from './PrivacyNotice';
import { declineConsent, loadConsent, resetConsentState, useConsentDecision, withdrawConsent } from './consentState';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
// "Delete everything" cancels notifications first; keep the real module (Expo Go push warning) out.
jest.mock('expo-notifications', () => ({ cancelAllScheduledNotificationsAsync: jest.fn(async () => undefined) }));

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

describe('privacy notice lines per tier (COMPLIANCE_PRIVACY §4.5)', () => {
  it('demo: no "goes to Google\'s AI (Gemini)" line next to "No AI service is contacted"', () => {
    const keys = privacyNoticeKeys('demo', 'ios');
    expect(keys).not.toContain('privacy.notice.sent');
    expect(keys[0]).toBe('consent.line2.demo');
  });

  it('paid, unpaid and unknown keep line 1 before their tier line', () => {
    expect(privacyNoticeKeys('paid', 'android').slice(0, 2)).toEqual(['privacy.notice.sent', 'consent.line2.paid']);
    expect(privacyNoticeKeys('unpaid', 'ios').slice(0, 2)).toEqual(['privacy.notice.sent', 'consent.line2.unpaid']);
    expect(privacyNoticeKeys('unknown', 'web').slice(0, 2)).toEqual(['privacy.notice.sent', 'consent.line2.unknown']);
    expect(privacyNoticeKeys('paid', 'web')).toContain('privacy.notice.device_web');
  });
});

describe('startRoute (S0)', () => {
  const record = { consent_version: '2026-10-01', accepted_at: 'x', tier_seen: 'paid' as const, platform: 'ios' as const };
  const base = { languageDecided: true, decision: 'accepted' as const, record, serverConsentVersion: '2026-10-01', tier: 'paid' as const };
  it('routes language → consent → tabs', () => {
    expect(startRoute({ ...base, languageDecided: false })).toBe('/onboarding/language');
    expect(startRoute({ ...base, decision: 'none', record: null })).toBe('/onboarding/consent');
    expect(startRoute(base)).toBe('/(tabs)');
    expect(startRoute({ ...base, decision: 'not_now', record: null })).toBe('/(tabs)');
  });
  it('re-shows consent on a new consent version or tier, not while offline', () => {
    expect(startRoute({ ...base, serverConsentVersion: '2026-10-15' })).toBe('/onboarding/consent');
    expect(startRoute({ ...base, tier: 'demo' })).toBe('/onboarding/consent');
    expect(startRoute({ ...base, tier: 'unknown', serverConsentVersion: null })).toBe('/(tabs)');
  });
});

describe('Delete everything forgets the consent decision (S17 item 8, COMPLIANCE_PRIVACY §9.5)', () => {
  beforeEach(async () => {
    resetConsentState();
    useSession.getState().reset();
    await kv.clearAll();
  });

  const routeAfterLanguage = () =>
    startRoute({
      languageDecided: true,
      decision: useConsentDecision.getState().decision,
      record: useSession.getState().consent,
      serverConsentVersion: null,
      tier: 'unknown',
    });

  it.each([
    ['not_now', declineConsent],
    ['withdrawn', withdrawConsent],
  ] as const)('after %s, a wipe sends the user back through S2', async (seen, choose) => {
    await loadConsent();
    await choose();
    expect(useConsentDecision.getState().decision).toBe(seen);
    await wipeEverything();
    expect(useConsentDecision.getState().decision).toBe('none');
    await loadConsent();
    expect(useConsentDecision.getState().decision).toBe('none');
    expect(useConsentDecision.getState().loaded).toBe(true);
    expect(routeAfterLanguage()).toBe('/onboarding/consent');
  });

  it('creates no install id after "Not now" (CL-010: only at acceptance)', async () => {
    await declineConsent();
    expect(await installIdForRequests()).toBeNull();
    expect(await kv.get(KV_KEYS.installId)).toBeNull();
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
    consent_version: '2026-10-01',
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
      consent_version: '2026-10-01',
      accepted_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T/),
      tier_seen: 'demo',
      platform: 'ios',
    });
    expect(useSession.getState().consent?.consent_version).toBe('2026-10-01');
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

  it('cached paid config but unreachable server → still "Cannot confirm" with Continue disabled', async () => {
    await kv.setJSON(KV_KEYS.serverConfig, { ...demoConfig(), provider: 'gemini', data_use_tier: 'paid' });
    const { findByTestId, getByTestId, queryByTestId } = await render(
      <AppProviders client={configClient(null)} staticMetrics>
        <ConsentScreen navigate={jest.fn()} />
      </AppProviders>,
    );
    expect(await findByTestId('tier-badge-unknown')).toBeTruthy();
    expect(queryByTestId('tier-badge-paid')).toBeNull();
    expect(useSession.getState().tier).toBe('unknown');
    // The cached config stays for display-only rows (S17 `state.cached`).
    expect(useSession.getState().serverConfig?.data_use_tier).toBe('paid');
    expect(getByTestId('consent-continue').props.accessibilityState).toMatchObject({ disabled: true });
  });
});
