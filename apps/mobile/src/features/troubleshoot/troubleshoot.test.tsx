// WP6 lane 6B — troubleshoot: one image only (never a PDF), goal cap, the credential-guard banner
// when `asks_for_credentials_or_payment`, the scam card first, and the offline sample path.

import { fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { TroubleshootResult } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';

import { buildTroubleshootRequest, clampGoal, NotAnImageError, parseMode } from './request';
import { askPersonHref, TroubleshootResultCards } from './ResultCards';
import { TroubleshootScreen } from './TroubleshootScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
// The expo-network jest mock's listener has no `remove()`; reachability is not under test here.
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

const portal = require('../../../assets/fixtures/portal_file_too_large.result.en.json') as TroubleshootResult;
const png = { mime_type: 'image/png' as const, data_base64: 'iVBORw0KGgo=', masks: [], rotation: 0 as const };

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return {
    baseUrl: 'http://127.0.0.1:8029',
    health: fail,
    getConfig: fail,
    getPack: fail,
    postPack: fail,
    analyze: fail,
    troubleshoot: fail,
    chat: fail,
    matchResources: fail,
    listResources: fail,
    getResource: fail,
    getRules: fail,
    quicksheetPdf: fail,
    feedback: fail,
    listFixtures: fail,
    fixturePageUrl: (id, n) => `http://127.0.0.1:8029/v1/demo/fixtures/${id}/pages/${n}`,
  };
}

describe('buildTroubleshootRequest', () => {
  it('never sends a PDF', () => {
    expect(() =>
      buildTroubleshootRequest({
        screenshot: { ...png, mime_type: 'application/pdf' },
        mode: 'portal',
        language: 'en',
        platform: 'web',
      }),
    ).toThrow(NotAnImageError);
  });

  it('caps the goal at 300 characters and drops the portal hint in scam mode', () => {
    const req = buildTroubleshootRequest({
      screenshot: png,
      mode: 'scam_check',
      goal: `  ${'a'.repeat(400)}  `,
      portalHint: 'bank',
      language: 'prs',
      platform: 'android',
    });
    expect(req.user_goal).toHaveLength(300);
    expect(req.portal_hint).toBeNull();
    expect(req.target_language).toBe('prs');
    expect(req.screenshot.mime_type).toBe('image/png');
    expect(clampGoal('   ')).toBeNull();
    expect(parseMode('scam_check')).toBe('scam_check');
    expect(parseMode('anything')).toBe('portal');
  });
});

describe('TroubleshootResultCards', () => {
  it('shows the credential-guard banner when the screen asks for credentials or payment', async () => {
    const result = { ...portal, asks_for_credentials_or_payment: true };
    const { getByTestId, getByText } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <TroubleshootResultCards result={result} />
      </AppProviders>,
    );
    expect(getByTestId('credential-guard-detected')).toBeTruthy();
    expect(getByText(/Only type them on the official website, never here\./)).toBeTruthy();
    expect(getByText('What this screen is')).toBeTruthy();
    // Native Bidi wraps the quote in isolate marks, so match a substring.
    expect(getByText(/File exceeds the maximum size of 5 MB/)).toBeTruthy();
  });

  it('puts the scam card first and links "Ask a person" to Help with the tags', async () => {
    const result: TroubleshootResult = {
      ...portal,
      scam_risk: 'likely',
      is_likely_scam: true,
      scam_reasons: ['gift_card'],
      resource_tags: ['scam_report', 'benefits_navigation'],
      needs_human_help: true,
    };
    const { getByText, queryByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <TroubleshootResultCards result={result} />
      </AppProviders>,
    );
    expect(getByText(/^Scam risk: likely/)).toBeTruthy();
    expect(getByText('Asks for gift cards')).toBeTruthy();
    expect(queryByTestId('credential-guard-detected')).toBeNull();
    expect(askPersonHref(result)).toBe('/help?tags=scam_report%2Cbenefits_navigation');
  });
});

describe('TroubleshootScreen', () => {
  const realFetch = globalThis.fetch;
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it('shows mode chips, the standing guard, and serves the recorded sample offline', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed')) as unknown as typeof fetch;
    const { getByText, getByTestId, findByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <TroubleshootScreen />
      </AppProviders>,
    );
    expect(getByText('Stuck on a website')).toBeTruthy();
    expect(getByText('Is this a scam?')).toBeTruthy();
    expect(getByTestId('credential-guard')).toBeTruthy();
    await fireEvent.press(getByTestId('troubleshoot-sample'));
    expect(await findByTestId('troubleshoot-result')).toBeTruthy();
    expect(getByText('Do this next')).toBeTruthy();
  });
});
