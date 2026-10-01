// Privacy copy per platform (PRODUCT_SPEC §9.5, COMPLIANCE_PRIVACY §10.2 / §17, CL-047(a)):
//   • web never says "on this phone" — the wipe offer, the "Delete everything" confirm, the paper
//     delete confirm and the lock-screen explanation use their `.web` keys;
//   • iOS never says papers stay "only" on this phone while iCloud Backup may copy the vault;
//   • saving on native never writes the unmasked original of a page with "Hide parts" boxes (D-19).
//
// The `.web` English copy is requested in the Phase 2B keys file (keys-mobile-vault-help.json) and
// merged into en.json afterwards. Until then `withWebCopy()` adds the same text to the English base
// for the UI tests; the one test marked POST-MERGE checks the bundled pack itself.

import { act, fireEvent, render } from '@testing-library/react-native';
import { Platform } from 'react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { VaultAndDataSettings } from '@/features/settings/VaultAndDataSettings';
import { BASE_STRINGS, translate } from '@/i18n/store';
import type { DocumentRow, Member, StoredDocument, StoredPageInput, Vault } from '@/storage/index';
import type { CapturedPage } from '@/store/session';
import { useSettings } from '@/store/settings';

import { emptyVaultText } from './members';
import { PapersScreen } from './PapersScreen';
import { nativeOnlyClaimUnsafe, platformKey, trustFooterText } from './platformCopy';
import { SaveToVaultSheet } from './SaveToVaultSheet';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
  useLocalSearchParams: () => ({}),
}));

jest.mock('@/api/offline', () => ({
  listFixturesWithFallback: async () => ({ fixtures: [], source: 'bundled' }),
  bundledFixtureThumbnail: () => null,
}));

/** Same text as keys-mobile-vault-help.json (the merge step adds it to en.json). */
const WEB_COPY: Record<string, string> = {
  'wipe.title.web': 'Delete everything in this browser?',
  'wipe.body.web': 'This removes all saved papers, members, reminders and settings from this browser. It cannot be undone.',
  'settings.wipe_offer.web': 'Do you also want to delete everything saved in this browser?',
  'vault.delete_confirm.web': 'Delete this paper from this browser?',
  'reminders.lockscreen_explain.web': "Off: calendar files only say a date is coming. On: they show the paper's name.",
};

function withWebCopy(): () => void {
  const added = Object.keys(WEB_COPY).filter((k) => !(k in BASE_STRINGS));
  for (const k of added) BASE_STRINGS[k] = WEB_COPY[k];
  return () => {
    for (const k of added) delete BASE_STRINGS[k];
  };
}

const t = (key: string, vars?: Record<string, string | number>) => translate(BASE_STRINGS, key, vars);
const IOS_INTERIM = BASE_STRINGS['vault.privacy_native'];

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8028', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function fakeVault(rows: DocumentRow[] = []) {
  const members: Member[] = [];
  const saved: { doc: StoredDocument; pages: StoredPageInput[] }[] = [];
  const none = () => Promise.resolve();
  const vault = {
    init: none,
    members: { list: async () => [...members], add: jest.fn(), rename: none, recolor: none, remove: none },
    documents: {
      list: async () => [...rows],
      get: async () => null,
      save: jest.fn(async (doc: StoredDocument, pages: StoredPageInput[]) => {
        saved.push({ doc, pages });
      }),
      move: none,
      remove: jest.fn(none),
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

async function asPlatform<T>(os: typeof Platform.OS, fn: () => Promise<T>): Promise<T> {
  const original = Platform.OS;
  Platform.OS = os;
  try {
    return await fn();
  } finally {
    Platform.OS = original;
  }
}

describe('platform copy helpers', () => {
  it('iOS never claims "stay only on this phone" until the vault is excluded from iCloud Backup', () => {
    expect(nativeOnlyClaimUnsafe('ios')).toBe(true);
    expect(nativeOnlyClaimUnsafe('android')).toBe(false);
    expect(trustFooterText(t, 'ios')).toBe(`${BASE_STRINGS['vault.privacy_server']} ${IOS_INTERIM}`);
    expect(emptyVaultText(t, 'ios')).toBe(IOS_INTERIM);
    for (const text of [trustFooterText(t, 'ios'), emptyVaultText(t, 'ios')]) expect(text).not.toMatch(/stay only/);
    // Android has `allowBackup: false`: the "only on this phone" copy is true there.
    expect(trustFooterText(t, 'android')).toBe(BASE_STRINGS['home.trust_footer']);
    expect(emptyVaultText(t, 'android')).toBe(BASE_STRINGS['vault.empty']);
    // Web says "in this browser".
    expect(trustFooterText(t, 'web')).toBe(BASE_STRINGS['home.trust_footer.web']);
    expect(emptyVaultText(t, 'web')).toBe(BASE_STRINGS['vault.empty.web']);
  });

  it('platformKey picks `<key>.web` on web only, and never a key that does not exist', () => {
    const restore = withWebCopy();
    try {
      expect(platformKey('wipe.title', 'web')).toBe('wipe.title.web');
      expect(platformKey('wipe.title', 'ios')).toBe('wipe.title');
      expect(platformKey('wipe.title', 'android')).toBe('wipe.title');
      for (const key of ['wipe.title', 'wipe.body', 'settings.wipe_offer', 'vault.delete_confirm', 'reminders.lockscreen_explain']) {
        const text = t(platformKey(key, 'web'));
        expect(text).not.toMatch(/phone|lock screen/);
      }
    } finally {
      restore();
    }
    expect(platformKey('btn.save', 'web')).toBe('btn.save');
  });

  // POST-MERGE (keys-mobile-vault-help.json → en.json): fails until the merge step has added the keys.
  it('POST-MERGE: the bundled English pack has every requested `.web` key with the requested text', () => {
    const bundled = require('@/i18n/packs/en.json') as Record<string, string>;
    for (const [key, text] of Object.entries(WEB_COPY)) expect([key, bundled[key]]).toEqual([key, text]);
  });
});

describe('web copy in the UI (CL-047(a))', () => {
  let restore: () => void = () => undefined;
  beforeEach(() => {
    restore = withWebCopy();
  });
  afterEach(() => restore());

  it('web "Delete everything" confirm and lock-screen explanation say "this browser"', async () => {
    const { vault } = fakeVault();
    await asPlatform('web', async () => {
      const { getByTestId, getByText, queryByText } = await render(
        <AppProviders client={offlineClient()} vault={vault} staticMetrics>
          <VaultAndDataSettings />
        </AppProviders>,
      );
      expect(getByText(WEB_COPY['reminders.lockscreen_explain.web'])).toBeTruthy();
      await act(async () => {
        fireEvent.press(getByTestId('settings-delete-everything'));
      });
      expect(getByText('Delete everything in this browser?')).toBeTruthy();
      expect(getByText(WEB_COPY['wipe.body.web'])).toBeTruthy();
      expect(queryByText(BASE_STRINGS['wipe.title'])).toBeNull();
      expect(queryByText(BASE_STRINGS['wipe.body'])).toBeNull();
      expect(queryByText(BASE_STRINGS['reminders.lockscreen_explain'])).toBeNull();
    });
  });

  it('native keeps the phone wording', async () => {
    const { vault } = fakeVault();
    const { getByTestId, getByText } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <VaultAndDataSettings />
      </AppProviders>,
    );
    await act(async () => {
      fireEvent.press(getByTestId('settings-delete-everything'));
    });
    expect(getByText('Delete everything on this phone?')).toBeTruthy();
  });

  it('web paper delete confirm says "from this browser"', async () => {
    const row: DocumentRow = {
      id: 'an_1',
      memberId: 'me',
      title: 'Medicaid letter',
      category: 'benefits',
      documentType: 'medicaid_renewal',
      createdAt: '2026-09-28T12:00:00.000Z',
      nextDateIso: null,
      pageCount: 1,
    };
    const { vault } = fakeVault([row]);
    await asPlatform('web', async () => {
      const { findByTestId, getByTestId, getByText, queryByText } = await render(
        <AppProviders client={offlineClient()} vault={vault} staticMetrics>
          <PapersScreen />
        </AppProviders>,
      );
      await act(async () => {
        fireEvent.press(await findByTestId('paper-options-an_1'));
      });
      await act(async () => {
        fireEvent.press(getByTestId('paper-menu-delete'));
      });
      expect(getByText('Delete this paper from this browser?')).toBeTruthy();
      expect(queryByText('Delete this paper from this phone?')).toBeNull();
    });
  });
});

describe('Save with "Hide parts" boxes (D-19)', () => {
  const analysis = {
    analysis_id: 'an_masked',
    category: 'immigration',
    document_type: 'uscis_receipt',
    demands: [],
    unverified: [],
    summary: { title: 'USCIS receipt', body: '', body_en: '', span_ids: [] },
    quality: { legibility: 'good', pages_received: 1, pages_unreadable: [], readable: true, reason: null },
    model_meta: { demo: false },
    page_thumbnails: null,
    sender_as_written: null,
    is_likely_scam: false,
  } as unknown as AnalysisResult;
  const maskedPage: CapturedPage = {
    id: 'p1',
    uri: 'file:///p1.jpg',
    base64: '/9j/UNMASKED_ORIGINAL_BYTES_WITH_SSN',
    mimeType: 'image/jpeg',
    rotation: 0,
    masks: [{ x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.2 }],
    source: 'camera',
  };

  async function saveWith(pages: CapturedPage[]) {
    const { vault, saved } = fakeVault();
    const { getByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <SaveToVaultSheet analysis={analysis} pages={pages} onSaved={jest.fn()} onCancel={jest.fn()} />
      </AppProviders>,
    );
    await act(async () => {
      fireEvent.press(getByTestId('save-to-vault-confirm'));
    });
    return saved;
  }

  it('native ("Keep page images" on by default): the unmasked original is never written', async () => {
    const saved = await saveWith([maskedPage]);
    expect(saved).toHaveLength(1);
    expect(saved[0].pages).toEqual([]);
    expect(JSON.stringify(saved)).not.toContain('UNMASKED_ORIGINAL_BYTES_WITH_SSN');
  });

  it('web: the display page already has the boxes burned in, so it may be kept', async () => {
    const before = useSettings.getState().keepPageImages;
    useSettings.setState({ keepPageImages: true });
    try {
      const burned: CapturedPage = { ...maskedPage, base64: 'QlVSTkVE' };
      const saved = await asPlatform('web', () => saveWith([burned]));
      expect(saved[0].pages).toEqual([{ page: 1, base64Jpeg: 'QlVSTkVE', thumbBase64: undefined }]);
    } finally {
      useSettings.setState({ keepPageImages: before });
    }
  });
});
