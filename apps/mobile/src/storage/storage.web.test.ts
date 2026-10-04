// Web vault (BUILD_PLAN §5.5 step 4): the in-memory path, and — with a small in-file IndexedDB fake,
// since fake-indexeddb is not installed — the opt-in paths: "Keep on this device" persists and
// reloads; "Clear when I close this tab" never writes IndexedDB, deletes any leftover database
// before loading, and clears on `pagehide` without awaiting anything (the browser does not run the
// page's later tasks after `pagehide`). Imports ./vault.web directly (never via the resolver).

import type { AnalysisResult } from '@/api/types';
import { consentStore } from '@/storage/consent';
import { memoryBlobCount } from '@/storage/files.web';
import { resetIdbForTests } from '@/storage/idb.web';
import type { StoredDocument } from '@/storage/index';
import { kv, KV_KEYS } from '@/storage/kv';
import { ME_MEMBER_ID } from '@/storage/rows';
import { configureVault, isPersistent, resetWebVaultForTests, vault } from '@/storage/vault.web';

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
    await vault.members.recolor(m.id, '#A33A06');
    expect((await vault.members.list()).find((x) => x.id === m.id)?.color).toBe('#A33A06');
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
      consent_version: '2026-10-04',
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

// --- a minimal IndexedDB fake (only what idb.web.ts calls) ------------------------------------

type Row = Record<string, unknown>;
type FakeStore = { keyPath: string | string[]; rows: Map<string, Row> };
type FakeDbState = Map<string, FakeStore>;

class FakeRequest<T = unknown> {
  result!: T;
  error: unknown = null;
  onsuccess: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onupgradeneeded: (() => void) | null = null;
  onblocked: (() => void) | null = null;
}

function later(fn: () => void): void {
  setTimeout(fn, 0);
}

function keyOf(store: FakeStore, value: Row): unknown {
  return Array.isArray(store.keyPath) ? store.keyPath.map((k) => value[k]) : value[store.keyPath];
}

function done<T>(value: T): FakeRequest<T> {
  const r = new FakeRequest<T>();
  later(() => {
    r.result = value;
    r.onsuccess?.();
  });
  return r;
}

function fakeIndexedDb() {
  const databases = new Map<string, FakeDbState>();
  const log: string[] = [];
  const connections = new Set<{ closed: boolean; onversionchange: (() => void) | null }>();
  function connection(state: FakeDbState) {
    const conn = {
      closed: false,
      onversionchange: null as (() => void) | null,
      objectStoreNames: { contains: (n: string) => state.has(n) },
      createObjectStore(name: string, opts: { keyPath: string | string[] }) {
        state.set(name, { keyPath: opts.keyPath, rows: new Map() });
      },
      transaction(name: string) {
        const store = state.get(name);
        if (!store) throw new Error(`no store ${name}`);
        return {
          objectStore: () => ({
            put(value: Row) {
              log.push(`put:${name}`);
              store.rows.set(JSON.stringify(keyOf(store, value)), value);
              return done(undefined);
            },
            get: (key: unknown) => done(store.rows.get(JSON.stringify(key))),
            getAll: () => done([...store.rows.values()]),
            getAllKeys: () => done([...store.rows.keys()].map((k) => JSON.parse(k) as unknown)),
            delete(key: unknown) {
              store.rows.delete(JSON.stringify(key));
              return done(undefined);
            },
          }),
        };
      },
      close() {
        conn.closed = true;
        connections.delete(conn);
      },
    };
    connections.add(conn);
    return conn;
  }
  const api = {
    open(name: string) {
      log.push(`open:${name}`);
      const r = new FakeRequest<unknown>();
      later(() => {
        const existed = databases.has(name);
        if (!existed) databases.set(name, new Map());
        r.result = connection(databases.get(name) as FakeDbState);
        if (!existed) r.onupgradeneeded?.();
        r.onsuccess?.();
      });
      return r;
    },
    deleteDatabase(name: string) {
      // Queued synchronously, like the real API; the data is gone once no connection is open.
      log.push(`deleteDatabase:${name}`);
      for (const c of [...connections]) c.onversionchange?.();
      databases.delete(name);
      return done(undefined);
    },
  };
  return { api, databases, log };
}

function seedLeftover(databases: Map<string, FakeDbState>, title: string): void {
  const docs: FakeStore = { keyPath: 'id', rows: new Map() };
  const row = doc('left-1', ME_MEMBER_ID, title, '2026-09-01T00:00:00Z') as unknown as Row;
  docs.rows.set(JSON.stringify('left-1'), row);
  const state: FakeDbState = new Map();
  for (const name of ['members', 'pages', 'checklist_state', 'reminders', 'meta', 'blobs']) {
    state.set(name, { keyPath: name === 'blobs' ? 'path' : 'id', rows: new Map() });
  }
  state.set('documents', docs);
  databases.set('proxyhealth', state);
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 5));

describe('web vault (IndexedDB opt-in)', () => {
  const g = globalThis as unknown as {
    indexedDB?: unknown;
    addEventListener?: unknown;
    removeEventListener?: unknown;
  };
  const saved = { add: g.addEventListener, remove: g.removeEventListener };
  let fake: ReturnType<typeof fakeIndexedDb>;
  let listeners: Map<string, Set<() => void>>;

  beforeEach(() => {
    resetWebVaultForTests();
    resetIdbForTests();
    fake = fakeIndexedDb();
    g.indexedDB = fake.api;
    listeners = new Map();
    g.addEventListener = (e: string, f: () => void) => {
      if (!listeners.has(e)) listeners.set(e, new Set());
      listeners.get(e)?.add(f);
    };
    g.removeEventListener = (e: string, f: () => void) => listeners.get(e)?.delete(f);
  });

  afterEach(() => {
    resetWebVaultForTests();
    resetIdbForTests();
    delete g.indexedDB;
    g.addEventListener = saved.add;
    g.removeEventListener = saved.remove;
  });

  it('keeping (clear-on-close off) writes IndexedDB and a new tab loads the papers back', async () => {
    await configureVault({ persist: 'indexeddb', clearOnClose: false });
    expect(isPersistent()).toBe(true);
    await vault.documents.save(doc('k1', ME_MEMBER_ID, 'Medicaid letter', '2026-09-01T00:00:00Z'), [
      { page: 1, base64Jpeg: PAGE_B64, thumbBase64: PAGE_B64 },
    ]);
    expect(fake.databases.get('proxyhealth')?.get('documents')?.rows.size).toBe(1);
    expect(fake.databases.get('proxyhealth')?.get('blobs')?.rows.size).toBe(2);
    expect(listeners.get('pagehide')?.size ?? 0).toBe(0);

    // A new tab: fresh module state, same browser storage.
    resetWebVaultForTests();
    resetIdbForTests();
    await configureVault({ persist: 'indexeddb', clearOnClose: false });
    expect((await vault.documents.list()).map((d) => d.id)).toEqual(['k1']);
  });

  it('clear-on-close never writes papers to IndexedDB and deletes a leftover database first', async () => {
    // What the old async pagehide wipe left behind on a shared computer.
    seedLeftover(fake.databases, 'Medicaid letter for Maria');
    await configureVault({ persist: 'indexeddb', clearOnClose: true });
    expect(isPersistent()).toBe(false);
    expect(fake.log).toContain('deleteDatabase:proxyhealth');
    expect(fake.databases.has('proxyhealth')).toBe(false);
    expect(await vault.documents.list()).toEqual([]);

    await vault.documents.save(doc('c1', ME_MEMBER_ID, 'Jury summons', '2026-09-02T00:00:00Z'), [
      { page: 1, base64Jpeg: PAGE_B64 },
    ]);
    await vault.members.add({ name: 'Rosa', color: '#A33A06' });
    await flush();
    expect(fake.log.filter((c) => c.startsWith('put:') || c.startsWith('open:'))).toEqual([]);
    expect(fake.databases.has('proxyhealth')).toBe(false);
    expect((await vault.documents.list()).map((d) => d.id)).toEqual(['c1']);
  });

  it('pagehide clears memory and queues deleteDatabase synchronously (no await survives unload)', async () => {
    await configureVault({ persist: 'indexeddb', clearOnClose: true });
    await vault.documents.save(doc('p1', ME_MEMBER_ID, 'Notice', '2026-09-03T00:00:00Z'), [
      { page: 1, base64Jpeg: PAGE_B64 },
    ]);
    const handlers = [...(listeners.get('pagehide') ?? [])];
    expect(handlers).toHaveLength(1);
    fake.log.length = 0;
    handlers[0]();
    // Checked before anything is awaited: the unloading page gets no later task.
    expect(fake.log).toEqual(['deleteDatabase:proxyhealth']);
    expect(memoryBlobCount()).toBe(0);
    expect(await vault.documents.list()).toEqual([]);
  });

  it('turning clear-on-close on while keeping: this tab keeps its papers, the database is deleted', async () => {
    await configureVault({ persist: 'indexeddb', clearOnClose: false });
    await vault.documents.save(doc('s1', ME_MEMBER_ID, 'Bill', '2026-09-04T00:00:00Z'), [
      { page: 1, base64Jpeg: PAGE_B64, thumbBase64: PAGE_B64 },
    ]);
    // Next tab: records load, page images stay in IndexedDB until shown.
    resetWebVaultForTests();
    resetIdbForTests();
    await configureVault({ persist: 'indexeddb', clearOnClose: false });
    expect(memoryBlobCount()).toBe(0);

    await configureVault({ persist: 'indexeddb', clearOnClose: true });
    expect(isPersistent()).toBe(false);
    expect(fake.databases.has('proxyhealth')).toBe(false);
    expect((await vault.documents.list()).map((d) => d.id)).toEqual(['s1']);
    expect(memoryBlobCount()).toBe(2);
    expect(listeners.get('pagehide')?.size).toBe(1);
  });

  it('back to "session": the database is deleted and the pagehide listener removed', async () => {
    await configureVault({ persist: 'indexeddb', clearOnClose: true });
    expect(listeners.get('pagehide')?.size).toBe(1);
    await configureVault({ persist: 'indexeddb', clearOnClose: false });
    expect(isPersistent()).toBe(true);
    expect(listeners.get('pagehide')?.size ?? 0).toBe(0);
    await configureVault({ persist: 'session', clearOnClose: true });
    expect(isPersistent()).toBe(false);
    expect(fake.databases.has('proxyhealth')).toBe(false);
    expect(listeners.get('pagehide')?.size ?? 0).toBe(0);
  });
});
