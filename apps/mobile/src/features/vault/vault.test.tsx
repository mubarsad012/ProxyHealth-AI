// WP6 lane 6A UI checks: saving is opt-in (nothing — not the paper, not a new member — is written
// before the "Whose paper is this?" sheet confirms), and Settings → saved papers renders its rows.

import { act, fireEvent, render } from '@testing-library/react-native';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { VaultAndDataSettings } from '@/features/settings/VaultAndDataSettings';
import type { Member, StoredDocument, StoredPageInput, Vault } from '@/storage/index';

import { SaveToVaultSheet } from './SaveToVaultSheet';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return new Proxy({ baseUrl: 'http://127.0.0.1:8028', fixturePageUrl: () => '' } as unknown as ApiClient, {
    get: (target, prop) => (prop in target ? target[prop as keyof ApiClient] : fail),
  });
}

function fakeVault() {
  const members: Member[] = [];
  const saved: { doc: StoredDocument; pages: StoredPageInput[] }[] = [];
  const none = () => Promise.resolve();
  const vault = {
    init: none,
    members: {
      list: async () => [...members],
      add: jest.fn(async ({ name, color }: { name: string; color: string }) => {
        const m = { id: `m${members.length + 1}`, name, color, createdAt: '2026-09-30T00:00:00Z' };
        members.push(m);
        return m;
      }),
      rename: none,
      remove: none,
    },
    documents: {
      list: async () => [],
      get: async () => null,
      save: jest.fn(async (doc: StoredDocument, pages: StoredPageInput[]) => {
        saved.push({ doc, pages });
      }),
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
  return { vault, members, saved };
}

const analysis = {
  analysis_id: 'an_test',
  category: 'benefits',
  document_type: 'medicaid_renewal',
  demands: [],
  unverified: [],
  summary: { title: 'Medicaid letter', body: '', body_en: '', span_ids: [] },
  quality: { legibility: 'good', pages_received: 1, pages_unreadable: [], readable: true, reason: null },
  model_meta: { demo: false },
  page_thumbnails: null,
  sender_as_written: null,
  is_likely_scam: false,
} as unknown as AnalysisResult;

describe('SaveToVaultSheet (opt-in save)', () => {
  it('writes nothing until Save, then saves for "Me"', async () => {
    const { vault, saved } = fakeVault();
    const onSaved = jest.fn();
    const { getByText, getByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <SaveToVaultSheet analysis={analysis} pages={[]} onSaved={onSaved} onCancel={jest.fn()} />
      </AppProviders>,
    );
    expect(getByText('Whose paper is this?')).toBeTruthy();
    expect(getByText('Me')).toBeTruthy();
    expect(vault.documents.save).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.press(getByTestId('save-to-vault-confirm'));
    });
    expect(saved).toHaveLength(1);
    expect(saved[0].doc.id).toBe('an_test');
    expect(saved[0].doc.memberId).toBe('me');
    expect(onSaved).toHaveBeenCalledWith('an_test');
  });

  it('creates a new person only when the paper is saved', async () => {
    const { vault, saved } = fakeVault();
    const onCancel = jest.fn();
    const { getByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <SaveToVaultSheet analysis={analysis} pages={[]} onSaved={jest.fn()} onCancel={onCancel} />
      </AppProviders>,
    );
    await act(async () => {
      fireEvent.press(getByTestId('save-add-member'));
    });
    await act(async () => {
      fireEvent.changeText(getByTestId('member-name-input'), 'Amir');
    });
    await act(async () => {
      fireEvent.press(getByTestId('member-form-submit'));
    });
    expect(vault.members.add).not.toHaveBeenCalled();
    await act(async () => {
      fireEvent.press(getByTestId('save-to-vault-confirm'));
    });
    expect(vault.members.add).toHaveBeenCalledTimes(1);
    expect(saved[0].doc.memberId).toBe('m1');
    expect(onCancel).not.toHaveBeenCalled();
  });
});

describe('VaultAndDataSettings', () => {
  it('renders saved-paper toggles, sample mode and Delete everything', async () => {
    const { vault } = fakeVault();
    const { getByText, getByTestId } = await render(
      <AppProviders client={offlineClient()} vault={vault} staticMetrics>
        <VaultAndDataSettings />
      </AppProviders>,
    );
    expect(getByText('Your saved papers')).toBeTruthy();
    expect(getByText('Keep page images')).toBeTruthy();
    expect(getByText('Hide ID numbers in saved copies')).toBeTruthy();
    expect(getByTestId('settings-sample-toggle')).toBeTruthy();
    await act(async () => {
      fireEvent.press(getByTestId('settings-delete-everything'));
    });
    expect(getByText('Delete everything on this phone?')).toBeTruthy();
  });
});
