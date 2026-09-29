// Web vault, in-memory path (BUILD_PLAN §5.5 step 4; fake-indexeddb is not installed, so the
// IndexedDB opt-in is checked manually). Imports ./vault.web directly (never via the resolver).

import type { AnalysisResult } from '@/api/types';
import { consentStore } from '@/storage/consent';
import { memoryBlobCount } from '@/storage/files.web';
import type { StoredDocument } from '@/storage/index';
import { kv, KV_KEYS } from '@/storage/kv';
import { ME_MEMBER_ID } from '@/storage/rows';
import { configureVault, isPersistent, vault } from '@/storage/vault.web';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

// Any base64 decodes to bytes for the Blob ("fake-jpeg-bytes").
const PAGE_B64 = 'ZmFrZS1qcGVnLWJ5dGVz';

function doc(id: string, memberId: string, title: string, createdAt: string): StoredDocument {
  return {
    id,
    memberId,
    title,
    category: 'benefits',
    documentType: 'medicaid_renewal',
    createdAt,
    nextDateIso: '2026-10-14',
    pageCount: 1,
    analysis: { sender_as_written: 'Virginia Department of Medical Assistance Services' } as AnalysisResult,
    keepPages: true,
  };
}

describe('web vault (memory)', () => {
  beforeEach(async () => {
    await vault.wipeAll();
    await kv.clearAll();
  });

  it('stays in memory unless IndexedDB is chosen and available', async () => {
    await configureVault({ persist: 'indexeddb', clearOnClose: true });
    expect(isPersistent()).toBe(false); // no indexedDB in the test environment
    await configureVault({ persist: 'session', clearOnClose: true });
    expect(isPersistent()).toBe(false);
  });

  it('members: add, rename, list; "Me" cannot be removed', async () => {
    const m = await vault.members.add({ name: 'Mariam', color: '#175E33' });
    await vault.members.rename(m.id, 'Mariam K');
    await vault.documents.save(doc('d-me', ME_MEMBER_ID, 'Letter', '2026-09-01T00:00:00Z'), []);
    const list = await vault.members.list();
    expect(list.map((x) => x.id).sort()).toEqual([ME_MEMBER_ID, m.id].sort());
    expect(list.find((x) => x.id === m.id)?.name).toBe('Mariam K');
    await vault.members.remove(ME_MEMBER_ID, true);
    expect((await vault.members.list()).some((x) => x.id === ME_MEMBER_ID)).toBe(true);
  });

  it('documents: save with pages, list newest first, search, move, remove cascades', async () => {
    const m = await vault.members.add({ name: 'Rosa', color: '#A33A06' });
    await vault.documents.save(doc('d1', m.id, 'Medicaid letter', '2026-09-01T00:00:00Z'), [
      { page: 1, base64Jpeg: PAGE_B64, thumbBase64: PAGE_B64 },
    ]);
    await vault.documents.save(doc('d2', m.id, 'Hospital bill', '2026-09-02T00:00:00Z'), []);
    expect((await vault.documents.list()).map((d) => d.id)).toEqual(['d2', 'd1']);
    expect((await vault.documents.list(m.id)).length).toBe(2);
    expect((await vault.documents.search('medical assistance')).map((d) => d.id)).toEqual(['d2', 'd1']);
    expect((await vault.documents.search('hospital')).map((d) => d.id)).toEqual(['d2']);

    const pages = await vault.pages.list('d1');
    expect(pages).toHaveLength(1);
    expect(pages[0].filePath).toBe('web://d1/page-1.jpg');
    expect(pages[0].thumbPath).toBe('web://d1/thumb-1.jpg');
    expect(memoryBlobCount()).toBe(2);

    await vault.checklist.set('d1', 'step-1', true);
    expect(await vault.checklist.get('d1')).toEqual({ 'step-1': true });
    const r = await vault.reminders.add({
      documentId: 'd1',
      demandId: 'dm1',
      fireAt: '2026-10-07T13:00:00Z',
      notificationId: null,
      detailOptIn: false,
      enabled: true,
      label: 'Answer by',
    });
    await vault.reminders.setEnabled(r.id, false);
    expect((await vault.reminders.list())[0].enabled).toBe(false);

    await vault.documents.move('d1', ME_MEMBER_ID);
    expect((await vault.documents.get('d1'))?.memberId).toBe(ME_MEMBER_ID);

    await vault.documents.remove('d1');
    expect(await vault.documents.get('d1')).toBeNull();
    expect(await vault.pages.list('d1')).toEqual([]);
    expect(await vault.checklist.get('d1')).toEqual({});
    expect(await vault.reminders.list()).toEqual([]);
    expect(memoryBlobCount()).toBe(0);
  });

  it('removing a member without wiping moves its papers to "Me"', async () => {
    const m = await vault.members.add({ name: 'Anh', color: '#1A4FC4' });
    await vault.documents.save(doc('d3', m.id, 'Denial letter', '2026-09-03T00:00:00Z'), []);
    await vault.members.remove(m.id, false);
    expect((await vault.documents.get('d3'))?.memberId).toBe(ME_MEMBER_ID);
    const m2 = await vault.members.add({ name: 'Jean', color: '#1A4FC4' });
    await vault.documents.save(doc('d4', m2.id, 'Bill', '2026-09-04T00:00:00Z'), []);
    await vault.members.remove(m2.id, true);
    expect(await vault.documents.get('d4')).toBeNull();
  });

  it('keepPages off stores no page files', async () => {
    await vault.documents.save({ ...doc('d5', ME_MEMBER_ID, 'No pages', '2026-09-05T00:00:00Z'), keepPages: false }, [
      { page: 1, base64Jpeg: PAGE_B64 },
    ]);
    expect(await vault.pages.list('d5')).toEqual([]);
    expect(memoryBlobCount()).toBe(0);
  });

  it('consent wraps kv (no vault table) and wipeAll leaves an empty state', async () => {
    const record = {
      consent_version: '2026-09-24',
      accepted_at: '2026-09-27T14:03:11Z',
      tier_seen: 'demo' as const,
      platform: 'web' as const,
    };
    await vault.consent.set(record);
    expect(await vault.consent.get()).toEqual(record);
    expect(await kv.getJSON(KV_KEYS.consent)).toEqual(record);
    expect(await consentStore.getDecision()).toBe('accepted');

    await vault.documents.save(doc('d6', ME_MEMBER_ID, 'Keep', '2026-09-06T00:00:00Z'), [{ page: 1, base64Jpeg: PAGE_B64 }]);
    await vault.wipeAll();
    expect(await vault.documents.list()).toEqual([]);
    expect(await vault.members.list()).toEqual([]);
    expect(await vault.reminders.list()).toEqual([]);
    expect(memoryBlobCount()).toBe(0);

    await vault.consent.clear();
    expect(await vault.consent.get()).toBeNull();
  });
});
