// WP6 lane 6B — troubleshoot: one image only (never a PDF), goal cap, the credential-guard banner
// when `asks_for_credentials_or_payment`, the scam card first, the offline sample path, and the
// consent gate (CL-070: no real screenshot is picked or sent before consent; the sample stays open).

import { act, fireEvent, render, waitFor } from '@testing-library/react-native';
import { router } from 'expo-router';
import { Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { Resource, ResourceMatchResponse, TroubleshootResult } from '@/api/types';
import { disclaimerKey } from '@/features/help/format';
import type { StoredDocument, StoredPageInput, Vault } from '@/storage';
import { AppProviders } from '@/design/components/Providers';
import { useConsentDecision } from '@/features/onboarding/consentState';
import { useSession } from '@/store/session';

import { buildTroubleshootRequest, clampGoal, NotAnImageError, parseMode } from './request';
import { buildEvidenceDocument, canSaveEvidence, saveScamEvidence } from './evidence';
import { pickScreenshot, type Screenshot } from './pick';
import { askPersonHref, TroubleshootResultCards } from './ResultCards';
import { revealResult } from './reveal';
import { reportingResources } from './ScamReport';
import { TroubleshootScreen } from './TroubleshootScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
// The expo-network jest mock's listener has no `remove()`; reachability is not under test here.
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
  useLocalSearchParams: () => ({}),
}));

// The system picker cannot run under jest; each test says what it "picks".
jest.mock('./pick', () => ({ ...jest.requireActual('./pick'), pickScreenshot: jest.fn() }));
// The result arrives below the fold: the screen hands its node to `revealResult` (reveal.test.ts).
jest.mock('./reveal', () => ({ ...jest.requireActual('./reveal'), revealResult: jest.fn() }));

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
    const { getByText, queryByTestId, findByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <TroubleshootResultCards result={result} />
      </AppProviders>,
    );
    expect(getByText(/^Scam risk: likely/)).toBeTruthy();
    // J-F: the reporting resources follow the scam card — from the DB (bundled subset offline).
    expect(await findByTestId('scam-report-resources')).toBeTruthy();
    expect(await findByTestId('resource-dhs_oig')).toBeTruthy();
    expect(queryByTestId('troubleshoot-save-evidence')).toBeNull();
    expect(getByText('Asks for gift cards')).toBeTruthy();
    expect(queryByTestId('credential-guard-detected')).toBeNull();
    expect(askPersonHref(result)).toBe('/help?tags=scam_report%2Cbenefits_navigation');
  });
});

const pickedShot: Screenshot = { uri: 'file:///picked.jpg', base64: '/9j/REAL_SCREENSHOT', mimeType: 'image/jpeg', width: 800, height: 1600 };

function acceptConsentForTest() {
  useConsentDecision.getState().set('accepted');
  useSession.getState().setConsent({
    consent_version: '2026-10-04',
    accepted_at: '2026-09-28T12:00:00.000Z',
    tier_seen: 'demo',
    platform: 'ios',
  });
}

describe('TroubleshootScreen', () => {
  const realFetch = globalThis.fetch;
  beforeEach(() => {
    jest.mocked(router.push).mockClear();
    jest.mocked(pickScreenshot).mockReset();
    jest.mocked(pickScreenshot).mockResolvedValue(pickedShot);
    useConsentDecision.getState().set('none');
    useSession.getState().setConsent(null);
  });
  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it('without consent: "Pick a screenshot" opens S2 and never opens the picker (CL-070)', async () => {
    const client = { ...offlineClient(), troubleshoot: jest.fn(() => Promise.reject(new Error('must not be called'))) };
    useConsentDecision.getState().set('not_now');
    const { getByTestId } = await render(
      <AppProviders client={client} staticMetrics>
        <TroubleshootScreen />
      </AppProviders>,
    );
    expect(getByTestId('troubleshoot-consent-needed')).toBeTruthy();
    await fireEvent.press(getByTestId('troubleshoot-pick'));
    expect(router.push).toHaveBeenCalledWith('/onboarding/consent');
    expect(pickScreenshot).not.toHaveBeenCalled();
    await fireEvent.press(getByTestId('troubleshoot-submit'));
    expect(client.troubleshoot).not.toHaveBeenCalled();
  });

  it('with consent the picked screenshot is sent; after "Stop sending papers" it is not (CL-070)', async () => {
    const troubleshoot = jest.fn(async () => portal);
    const client = { ...offlineClient(), troubleshoot };
    acceptConsentForTest();
    const { getByTestId, queryByTestId, findByTestId } = await render(
      <AppProviders client={client} staticMetrics>
        <TroubleshootScreen />
      </AppProviders>,
    );
    expect(queryByTestId('troubleshoot-consent-needed')).toBeNull();
    await fireEvent.press(getByTestId('troubleshoot-pick'));
    expect(pickScreenshot).toHaveBeenCalledTimes(1);
    await fireEvent.press(getByTestId('troubleshoot-submit'));
    expect(await findByTestId('troubleshoot-result')).toBeTruthy();
    expect(troubleshoot).toHaveBeenCalledTimes(1);
    expect(troubleshoot.mock.calls[0]).toEqual([
      expect.objectContaining({ screenshot: expect.objectContaining({ data_base64: pickedShot.base64 }), demo_sample_id: null }),
    ]);
    expect(router.push).not.toHaveBeenCalledWith('/onboarding/consent');

    // Consent withdrawn while the screenshot is still on screen: nothing is sent, S2 opens.
    await act(async () => {
      useConsentDecision.getState().set('withdrawn');
      useSession.getState().setConsent(null);
    });
    await fireEvent.press(getByTestId('troubleshoot-submit'));
    expect(troubleshoot).toHaveBeenCalledTimes(1);
    expect(router.push).toHaveBeenCalledWith('/onboarding/consent');
  });

  it('shows mode chips, the standing guard, and serves the recorded sample offline (before consent too)', async () => {
    globalThis.fetch = jest.fn().mockRejectedValue(new TypeError('Network request failed')) as unknown as typeof fetch;
    const { getByText, getByTestId, findByTestId } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <TroubleshootScreen />
      </AppProviders>,
    );
    expect(getByText('Stuck on a website')).toBeTruthy();
    expect(getByText('Is this a scam?')).toBeTruthy();
    expect(getByTestId('credential-guard')).toBeTruthy();
    jest.mocked(revealResult).mockClear();
    await fireEvent.press(getByTestId('troubleshoot-sample'));
    expect(await findByTestId('troubleshoot-result')).toBeTruthy();
    expect(getByText('Do this next')).toBeTruthy();
    expect(router.push).not.toHaveBeenCalledWith('/onboarding/consent');
    // The new result is brought into view (and focused) once, with its own block's node.
    // (Only the node's testID is compared: printing a node would walk the whole tree.)
    await waitFor(() => expect(jest.mocked(revealResult).mock.calls.length).toBe(1));
    const [node, opts] = jest.mocked(revealResult).mock.calls[0];
    expect((node as { props?: { testID?: string } } | null)?.props?.testID).toBe('troubleshoot-result-block');
    expect(opts).toEqual({ smooth: true });
    jest.mocked(revealResult).mockClear();
  });
});

const fallbacks = require('../../../assets/resources/national_fallbacks.json') as Resource[];
const byId = (id: string) => fallbacks.find((r) => r.id === id) as Resource;
const jpegShot: Screenshot = { uri: 'file:///shot.jpg', base64: '/9j/4AAQSkZJRg==', mimeType: 'image/jpeg', width: 800, height: 1600 };

describe('scam reporting resources', () => {
  it('lists scam_report DB entries first, de-duplicated, at most three', () => {
    const data: ResourceMatchResponse = {
      results: [{ resource: byId('dhs_oig'), score: 1, why_keys: [], why: [], eligibility_note_key: null, checklist: [] }],
      national_fallbacks: [byId('dhs_oig'), byId('ftc_reportfraud'), byId('211')],
      notes_keys: [],
      disclaimer_kind: 'general_information',
      resource_db_version: 'test',
    };
    expect(reportingResources(data).map((r) => r.id)).toEqual(['dhs_oig', 'ftc_reportfraud']);
    expect(reportingResources({ ...data, results: [], national_fallbacks: [byId('211')] }).map((r) => r.id)).toEqual(['211']);
    expect(reportingResources(null)).toEqual([]);
  });

  it('never shows a raw disclaimer key for banner-only kinds', () => {
    expect(disclaimerKey('general_information')).toBe('disclaimer.general_information');
    expect(disclaimerKey('demo_sample')).toBe('disclaimer.general_information');
    expect(disclaimerKey(null)).toBe('disclaimer.general_information');
  });
});

describe('Save as proof', () => {
  it('stores only the JPEG screenshot as a scam check (no analysis) on explicit save', async () => {
    expect(canSaveEvidence(jpegShot)).toBe(true);
    expect(canSaveEvidence({ ...jpegShot, mimeType: 'image/png' })).toBe(false);
    expect(canSaveEvidence(null)).toBe(false);
    const { doc, pages } = buildEvidenceDocument(jpegShot, { title: 'Scam check', now: new Date('2026-09-27T12:00:00Z'), id: 'doc_1' });
    expect(doc).toMatchObject({
      id: 'doc_1',
      title: 'Scam check',
      category: 'immigration',
      documentType: 'other_notice',
      nextDateIso: null,
      pageCount: 1,
      keepPages: true,
    });
    expect(doc.analysis).toBeNull();
    expect(pages).toEqual([{ page: 1, base64Jpeg: jpegShot.base64 }]);

    const saved: { doc: StoredDocument; pages: StoredPageInput[] }[] = [];
    const vault = { documents: { save: async (d: StoredDocument, p: StoredPageInput[]) => void saved.push({ doc: d, pages: p }) } };
    const id = await saveScamEvidence(vault as unknown as Vault, jpegShot, { title: 'Scam check' });
    expect(saved).toHaveLength(1);
    expect(saved[0].doc.id).toBe(id);
  });

  it('renders the button in the result cards and calls onSave', async () => {
    const onSave = jest.fn();
    const result: TroubleshootResult = { ...portal, scam_risk: 'possible', is_likely_scam: false };
    const { findByTestId, getByText } = await render(
      <AppProviders client={offlineClient()} staticMetrics>
        <TroubleshootResultCards result={result} evidence={{ onSave, saved: false, busy: false, failed: false }} />
      </AppProviders>,
    );
    await fireEvent.press(await findByTestId('troubleshoot-save-evidence'));
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(getByText('Save as proof')).toBeTruthy();
  });

  it('announces the save truthfully per platform (web never says "on this phone")', async () => {
    const result: TroubleshootResult = { ...portal, scam_risk: 'possible', is_likely_scam: false };
    const savedState = { onSave: jest.fn(), saved: true, busy: false, failed: false, member: 'Ana' };
    const originalOS = Platform.OS;
    try {
      Platform.OS = 'ios';
      const native = await render(
        <AppProviders client={offlineClient()} staticMetrics>
          <TroubleshootResultCards result={result} evidence={savedState} />
        </AppProviders>,
      );
      expect(native.getByText('Saved. It stays on this phone. Saved for Ana')).toBeTruthy();
      await native.unmount();

      Platform.OS = 'web';
      const web = await render(
        <AppProviders client={offlineClient()} staticMetrics>
          <TroubleshootResultCards result={result} evidence={savedState} />
        </AppProviders>,
      );
      expect(web.getByText('Saved for Ana')).toBeTruthy();
      expect(web.queryByText(/on this phone/)).toBeNull();
    } finally {
      Platform.OS = originalOS;
    }
  });
});
