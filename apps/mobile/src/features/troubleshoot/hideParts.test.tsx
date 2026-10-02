// Phase 2C — S16: "Hide parts" on the screenshot preview (S5's MaskEditor; boxes sent like S5:
// web burns them on a canvas and sends `masks: []`, native sends `masks[]`), and "Save as proof"
// asking "Whose paper is this?" (default Me) before anything is written.

import { fireEvent, render, waitFor } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { MaskRect, TroubleshootResult } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { useConsentDecision } from '@/features/onboarding/consentState';
import type { Member, StoredDocument, StoredPageInput, Vault } from '@/storage';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

import { cleanMasks, prepareScreenshot, screenshotPage } from './masks';
import { pickScreenshot, type Screenshot } from './pick';
import { TroubleshootScreen } from './TroubleshootScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));
jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
  useLocalSearchParams: () => ({}),
}));
jest.mock('./pick', () => ({ ...jest.requireActual('./pick'), pickScreenshot: jest.fn() }));
// The real editor is a drag surface; this stand-in adds one box the way it reports boxes.
const BOX: MaskRect = { x0: 0.1, y0: 0.2, x1: 0.6, y1: 0.4 };
jest.mock('@/features/scan/MaskEditor', () => {
  const { Pressable: MockPressable } = jest.requireActual<typeof import('react-native')>('react-native');
  const mockBox = { x0: 0.1, y0: 0.2, x1: 0.6, y1: 0.4 };
  return {
    MaskEditor: (props: { page: { masks: unknown[] }; onChange(m: unknown[]): void; onClose(): void }) => (
      <MockPressable
        testID="fake-mask-editor"
        onPress={() => {
          props.onChange([...props.page.masks, mockBox]);
          props.onClose();
        }}
      />
    ),
  };
});

const portal = require('../../../assets/fixtures/portal_file_too_large.result.en.json') as TroubleshootResult;
const shot: Screenshot = { uri: 'file:///picked.jpg', base64: '/9j/REAL_SCREENSHOT', mimeType: 'image/jpeg', width: 800, height: 1600 };

function client(troubleshoot: ApiClient['troubleshoot']): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8046', fixturePageUrl: () => '', troubleshoot } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function fakeVault(members: Member[] = []) {
  const saved: { doc: StoredDocument; pages: StoredPageInput[] }[] = [];
  const none = () => Promise.resolve();
  const vault = {
    init: none,
    members: { list: async () => [...members], add: jest.fn(), rename: none, remove: none },
    documents: {
      list: async () => [],
      get: async () => null,
      save: jest.fn(async (doc: StoredDocument, pages: StoredPageInput[]) => void saved.push({ doc, pages })),
      move: none,
      remove: none,
      search: async () => [],
    },
    pages: { list: async () => [], uri: async () => null },
    checklist: { get: async () => ({}), set: none },
    reminders: { list: async () => [], add: jest.fn(), remove: none, setEnabled: none },
    consent: { get: async () => null, set: none, clear: none },
    wipeAll: none,
  } as unknown as Vault;
  return { vault, saved };
}

function acceptConsent() {
  useConsentDecision.getState().set('accepted');
  useSession.getState().setConsent({ consent_version: '2026-10-01', accepted_at: '2026-10-01T12:00:00.000Z', tier_seen: 'demo', platform: 'ios' });
}

describe('prepareScreenshot (same mask rules as S5)', () => {
  it('no boxes: the screenshot as picked, and it may be kept as proof', async () => {
    const out = await prepareScreenshot(shot, [], 'ios');
    expect(out.input).toEqual({ mime_type: 'image/jpeg', data_base64: shot.base64, masks: [], rotation: 0 });
    expect(out.proof).toBe(shot);
  });

  it('native: normalised masks[] travel with the bytes; no proof image (it is unmasked)', async () => {
    const burn = jest.fn();
    const out = await prepareScreenshot(shot, [{ x0: 0.6, y0: 0.4, x1: 0.1, y1: 0.2 }, { x0: 0.5, y0: 0.5, x1: 0.5, y1: 0.5 }], 'android', { burn });
    expect(out.input.masks).toEqual([BOX]);
    expect(out.input.data_base64).toBe(shot.base64);
    expect(out.proof).toBeNull();
    expect(burn).not.toHaveBeenCalled();
  });

  it('web: burned on a canvas, masks: [] and the burned copy is the proof', async () => {
    const burn = jest.fn(async () => 'BURNED');
    const out = await prepareScreenshot(shot, [BOX], 'web', { burn });
    expect(burn).toHaveBeenCalledWith(shot.base64, [BOX]);
    expect(out.input).toEqual({ mime_type: 'image/jpeg', data_base64: 'BURNED', masks: [], rotation: 0 });
    expect(out.proof).toMatchObject({ base64: 'BURNED', mimeType: 'image/jpeg', uri: 'data:image/jpeg;base64,BURNED' });
  });

  it('web: a failed burn rejects, so unmasked pixels are never sent', async () => {
    await expect(prepareScreenshot(shot, [BOX], 'web', { burn: () => Promise.reject(new Error('canvas')) })).rejects.toThrow('canvas');
  });

  it('the editor page is the screenshot, unrotated, with its boxes', () => {
    expect(screenshotPage(shot, [BOX])).toMatchObject({ uri: shot.uri, rotation: 0, masks: [BOX], mimeType: 'image/jpeg' });
    expect(cleanMasks([{ x0: 0, y0: 0, x1: 0.001, y1: 1 }])).toEqual([]);
  });
});

describe('TroubleshootScreen: Hide parts and Save as proof', () => {
  beforeEach(() => {
    jest.mocked(pickScreenshot).mockReset();
    jest.mocked(pickScreenshot).mockResolvedValue(shot);
    acceptConsent();
    useSettings.setState({ hideIdNumbers: false });
  });

  it('boxes drawn on the preview are sent as masks (native)', async () => {
    const troubleshoot = jest.fn(async () => portal);
    const { getByTestId, findByTestId } = await render(
      <AppProviders client={client(troubleshoot)} vault={fakeVault().vault} staticMetrics>
        <TroubleshootScreen />
      </AppProviders>,
    );
    await fireEvent.press(await findByTestId('troubleshoot-pick'));
    await fireEvent.press(await findByTestId('troubleshoot-hide-parts'));
    await fireEvent.press(getByTestId('fake-mask-editor'));
    expect(getByTestId('troubleshoot-mask-0')).toBeTruthy();
    await fireEvent.press(getByTestId('troubleshoot-submit'));
    await waitFor(() => expect(troubleshoot).toHaveBeenCalledTimes(1));
    expect(troubleshoot.mock.calls[0]).toEqual([expect.objectContaining({ screenshot: expect.objectContaining({ masks: [BOX] }) })]);
  });

  it('"Save as proof" asks whose paper it is (default Me) and writes nothing before Save', async () => {
    const scam: TroubleshootResult = { ...portal, scam_risk: 'likely', is_likely_scam: true, model_meta: { ...portal.model_meta, demo: false } };
    const troubleshoot = jest.fn(async () => scam);
    const { vault, saved } = fakeVault([{ id: 'm1', name: 'Ana', color: '#336699', createdAt: '2026-10-01T00:00:00Z' }]);
    const { getByTestId, findByTestId, findByText } = await render(
      <AppProviders client={client(troubleshoot)} vault={vault} staticMetrics>
        <TroubleshootScreen initialMode="scam_check" />
      </AppProviders>,
    );
    await fireEvent.press(await findByTestId('troubleshoot-pick'));
    await findByTestId('troubleshoot-preview');
    await fireEvent.press(getByTestId('troubleshoot-submit'));
    await fireEvent.press(await findByTestId('troubleshoot-save-evidence'));
    expect(await findByTestId('save-to-vault-sheet')).toBeTruthy();
    expect(await findByText('Whose paper is this?')).toBeTruthy();
    expect(saved).toHaveLength(0);
    await fireEvent.press(await findByTestId('save-member-m1'));
    await fireEvent.press(getByTestId('save-to-vault-confirm'));
    await waitFor(() => expect(saved).toHaveLength(1));
    expect(saved[0].doc).toMatchObject({ memberId: 'm1', category: 'immigration', documentType: 'other_notice', analysis: null });
    expect(saved[0].pages).toEqual([{ page: 1, base64Jpeg: shot.base64 }]);
    expect(await findByText(/Saved for Ana/)).toBeTruthy();
  });

  it('native with boxes: no proof is offered (the stored image would be unmasked)', async () => {
    const scam: TroubleshootResult = { ...portal, scam_risk: 'likely', is_likely_scam: true, model_meta: { ...portal.model_meta, demo: false } };
    const { getByTestId, findByTestId, queryByTestId } = await render(
      <AppProviders client={client(jest.fn(async () => scam))} vault={fakeVault().vault} staticMetrics>
        <TroubleshootScreen initialMode="scam_check" />
      </AppProviders>,
    );
    await fireEvent.press(await findByTestId('troubleshoot-pick'));
    await fireEvent.press(await findByTestId('troubleshoot-hide-parts'));
    await fireEvent.press(getByTestId('fake-mask-editor'));
    await fireEvent.press(getByTestId('troubleshoot-submit'));
    expect(await findByTestId('troubleshoot-result')).toBeTruthy();
    expect(queryByTestId('troubleshoot-save-evidence')).toBeNull();
  });
});
