// WP6 lane 6A screen checks for S12/S13 and the sample picker: the empty vault explains that nothing
// is saved until Save; deleting a paper needs a confirm; "Me" can never be deleted while another
// person's delete wipes their papers (`members.remove(id, true)`); "Change color" recolours a member
// through `members.recolor` and the list re-reads; the sample picker lists the bundled manifest when
// the server is unreachable and hands back display-only pages.

import { act, fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { DemoFixture } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { SamplePicker } from '@/features/demo/SamplePicker';
import { resetSamplesCache } from '@/features/demo/sampleCache';
import type { DocumentRow, Member, Vault } from '@/storage/index';

import { MemberScreen } from './MemberScreen';
import { MEMBER_COLORS } from './members';
import { PapersScreen } from './PapersScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { push: jest.fn(), back: jest.fn(), replace: jest.fn(), canGoBack: () => false },
}));

// jest-expo runs as iOS: until the vault is excluded from iCloud Backup (COMPLIANCE_PRIVACY §10.2)
// the empty state shows the D-22 interim line, never "stay only on this phone" (platformCopy.ts).
const EMPTY_LINE_IOS = "Papers you save stay on this phone, protected by your phone's own encryption. Turn on a phone passcode.";

const BUNDLED: DemoFixture[] = [
  {
    id: 'portal_file_too_large',
    kind: 'screenshot',
    title_key: 'fixture.portal_file_too_large',
    title_en: 'Benefits website: file too large',
    pages: 1,
    thumbnail_url: '',
    available_target_languages: ['en'],
  } as unknown as DemoFixture,
  {
    id: 'medicaid_address_confirmation',
    kind: 'document',
    title_key: 'fixture.medicaid_address_confirmation',
    title_en: 'Medicaid address letter',
    pages: 1,
    thumbnail_url: '',
    available_target_languages: ['en'],
  } as unknown as DemoFixture,
];

// `@/api/offline` imports the synced `assets/fixtures` bundle, which jest cannot map (CL-033).
jest.mock('@/api/offline', () => ({
  listFixturesWithFallback: async (client: { listFixtures(): Promise<unknown> }) => {
    try {
      return { fixtures: await client.listFixtures(), source: 'server' };
    } catch {
      return { fixtures: BUNDLED, source: 'bundled' };
    }
  },
  bundledFixtureThumbnail: () => 'bundled-thumb.png',
}));

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8028', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

const ROW: DocumentRow = {
  id: 'an_1',
  memberId: 'm1',
  title: 'Medicaid letter',
  category: 'benefits',
  documentType: 'medicaid_renewal',
  createdAt: '2026-09-28T12:00:00.000Z',
  nextDateIso: null,
  pageCount: 1,
};

function fakeVault(opts: { members?: Member[]; rows?: DocumentRow[] } = {}) {
  const members = [...(opts.members ?? [])];
  const rows = [...(opts.rows ?? [])];
  const none = () => Promise.resolve();
  const vault = {
    init: none,
    members: {
      list: async () => [...members],
      add: jest.fn(),
      rename: jest.fn(none),
      recolor: jest.fn(async (id: string, color: string) => {
        const i = members.findIndex((m) => m.id === id);
        if (i >= 0) members[i] = { ...members[i], color };
      }),
      remove: jest.fn(async (id: string) => {
        const i = members.findIndex((m) => m.id === id);
        if (i >= 0) members.splice(i, 1);
      }),
    },
    documents: {
      list: async (memberId?: string) => rows.filter((r) => !memberId || r.memberId === memberId),
      get: async () => null,
      save: jest.fn(),
      move: jest.fn(none),
      remove: jest.fn(async (id: string) => {
        const i = rows.findIndex((r) => r.id === id);
        if (i >= 0) rows.splice(i, 1);
      }),
      search: async () => [],
    },
    pages: { list: async () => [], uri: async () => null },
    checklist: { get: async () => ({}), set: none },
    reminders: { list: async () => [], add: jest.fn(), remove: none, setEnabled: none },
    consent: { get: async () => null, set: none, clear: none },
    wipeAll: none,
  } as unknown as Vault;
  return { vault };
}

const AMIR: Member = { id: 'm1', name: 'Amir', color: '#A61B1B', createdAt: '2026-09-27T10:00:00.000Z' };

describe('S12 My papers', () => {
  it('explains that nothing is saved until Save when the vault is empty', async () => {
    const { vault } = fakeVault();
    const { findByText, getByText } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <PapersScreen />
      </AppProviders>,
    );
    expect(await findByText(EMPTY_LINE_IOS)).toBeTruthy();
    expect(getByText('Me')).toBeTruthy();
  });

  it('deletes a paper only after the confirm', async () => {
    const { vault } = fakeVault({ members: [AMIR], rows: [ROW] });
    const { findByTestId, getByTestId } = await render(
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
    expect(vault.documents.remove).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.press(getByTestId('paper-delete-confirm-confirm'));
    });
    expect(vault.documents.remove).toHaveBeenCalledWith('an_1');
  });
});

describe('S13 member detail', () => {
  it('never offers to delete "Me"', async () => {
    const { vault } = fakeVault({ members: [AMIR] });
    const { findByText, queryByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <MemberScreen memberId="me" />
      </AppProviders>,
    );
    expect(await findByText(EMPTY_LINE_IOS)).toBeTruthy();
    expect(queryByTestId('member-delete')).toBeNull();
  });

  it('"Change color" recolours the person with the swatch they pick', async () => {
    const { vault } = fakeVault({ members: [AMIR] });
    const { findByTestId, getByTestId, queryByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <MemberScreen memberId="m1" />
      </AppProviders>,
    );
    await act(async () => {
      fireEvent.press(await findByTestId('member-recolor'));
    });
    // Amir's current colour is the checked radio.
    expect(getByTestId('member-recolor-swatch-1').props.accessibilityState).toMatchObject({ checked: true });
    await act(async () => {
      fireEvent.press(getByTestId('member-recolor-swatch-2'));
    });
    expect(vault.members.recolor).toHaveBeenCalledWith('m1', MEMBER_COLORS[2]);
    expect(queryByTestId('member-recolor-panel')).toBeNull();
    // The list re-read after bumpVault(): reopening shows the new colour checked.
    await act(async () => {
      fireEvent.press(getByTestId('member-recolor'));
    });
    expect(getByTestId('member-recolor-swatch-2').props.accessibilityState).toMatchObject({ checked: true });
  });

  it('offers no "Change color" before the "Me" row exists', async () => {
    const { vault } = fakeVault();
    const { findByText, queryByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <MemberScreen memberId="me" />
      </AppProviders>,
    );
    expect(await findByText(EMPTY_LINE_IOS)).toBeTruthy();
    expect(queryByTestId('member-recolor')).toBeNull();
    expect(vault.members.recolor).not.toHaveBeenCalled();
  });

  it('"Move all papers" moves every paper to the person picked (never back to the same person)', async () => {
    const second: DocumentRow = { ...ROW, id: 'an_2', title: 'Clinic bill' };
    const { vault } = fakeVault({ members: [AMIR], rows: [ROW, second] });
    const { findByTestId, getByTestId, queryByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <MemberScreen memberId="m1" />
      </AppProviders>,
    );
    await act(async () => {
      fireEvent.press(await findByTestId('member-move-all'));
    });
    expect(queryByTestId('move-to-m1')).toBeNull();
    await act(async () => {
      fireEvent.press(getByTestId('move-to-me'));
    });
    expect(vault.documents.move).toHaveBeenCalledTimes(2);
    expect(vault.documents.move).toHaveBeenCalledWith('an_1', 'me');
    expect(vault.documents.move).toHaveBeenCalledWith('an_2', 'me');
  });

  it('deleting a person removes them with all their papers after the confirm', async () => {
    const { vault } = fakeVault({ members: [AMIR], rows: [ROW] });
    const { findByTestId, getByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <MemberScreen memberId="m1" />
      </AppProviders>,
    );
    await act(async () => {
      fireEvent.press(await findByTestId('member-delete'));
    });
    expect(vault.members.remove).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.press(getByTestId('member-delete-confirm-confirm'));
    });
    expect(vault.members.remove).toHaveBeenCalledWith('m1', true);
  });
});

describe('SamplePicker', () => {
  beforeEach(() => resetSamplesCache());

  it('lists the bundled samples offline, Medicaid first, and returns display-only pages', async () => {
    const { vault } = fakeVault();
    const onPick = jest.fn();
    const { findByTestId, getByText } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <SamplePicker onPick={onPick} />
      </AppProviders>,
    );
    const medicaid = await findByTestId('sample-medicaid_address_confirmation');
    expect(getByText('A screenshot of a website')).toBeTruthy();
    await act(async () => {
      fireEvent.press(medicaid);
    });
    expect(onPick).toHaveBeenCalledTimes(1);
    const [fixture, pages] = onPick.mock.calls[0];
    expect(fixture.id).toBe('medicaid_address_confirmation');
    expect(pages).toHaveLength(1);
    expect(pages[0]).toMatchObject({ source: 'sample', uri: 'bundled-thumb.png', masks: [] });
  });
});
