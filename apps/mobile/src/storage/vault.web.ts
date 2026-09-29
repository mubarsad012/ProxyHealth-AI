// Web vault (D-23, PRODUCT_SPEC §9.4): in-memory Maps for the tab session by default; after the
// user opts into "Keep on this device (not encrypted by the app)" every record is also written to
// IndexedDB `proxyhealth` (idb.web.ts) and loaded back on the next visit. "Clear when I close this
// tab" wipes memory + IndexedDB on `pagehide`. No secrets on web. Consent wraps `kv` (D-22).

import type { DocumentRow, Member, Reminder, StoredDocument, StoredPage, Vault } from '@/storage/index';
import { consentStore } from '@/storage/consent';
import * as files from '@/storage/files.web';
import {
  deleteIdb,
  idbAll,
  idbDelete,
  idbDeletePrefix,
  idbGet,
  idbPut,
  indexedDbAvailable,
  type StoreName,
} from '@/storage/idb.web';
import { byCreatedDesc, documentMatches, ME_MEMBER_ID } from '@/storage/rows';

export type VaultConfig = { persist: 'session' | 'indexeddb'; clearOnClose: boolean };

interface ChecklistRecord {
  documentId: string;
  stepId: string;
  checked: boolean;
}

const mem = {
  members: new Map<string, Member>(),
  documents: new Map<string, StoredDocument>(),
  pages: new Map<string, StoredPage>(),
  checklist: new Map<string, ChecklistRecord>(),
  reminders: new Map<string, Reminder>(),
  meta: new Map<string, string>(),
};

let persistent = false;
let pagehideListener: (() => void) | null = null;

const pageKey = (documentId: string, page: number) => `${documentId}|${page}`;
const checklistKey = (documentId: string, stepId: string) => `${documentId}|${stepId}`;

async function put(store: StoreName, value: unknown): Promise<void> {
  if (!persistent) return;
  try {
    await idbPut(store, value);
  } catch {
    // quota / private mode: memory copy still works for this session
  }
}

async function del(store: StoreName, key: IDBValidKey): Promise<void> {
  if (!persistent) return;
  try {
    await idbDelete(store, key);
  } catch {
    // ignore
  }
}

const idbBlobSink: files.BlobSink = {
  put: (path, blob) => put('blobs', { path, blob }),
  get: async (path) => (await idbGet<{ path: string; blob: Blob }>('blobs', path))?.blob ?? null,
  remove: (prefix) => (persistent ? idbDeletePrefix('blobs', prefix).catch(() => undefined) : Promise.resolve()),
};

async function loadFromIdb(): Promise<void> {
  const [members, documents, pages, checklist, reminders, meta] = await Promise.all([
    idbAll<Member>('members'),
    idbAll<StoredDocument>('documents'),
    idbAll<StoredPage>('pages'),
    idbAll<ChecklistRecord>('checklist_state'),
    idbAll<Reminder>('reminders'),
    idbAll<{ key: string; value: string }>('meta'),
  ]);
  members.forEach((m) => mem.members.set(m.id, m));
  documents.forEach((d) => mem.documents.set(d.id, d));
  pages.forEach((p) => mem.pages.set(pageKey(p.documentId, p.page), p));
  checklist.forEach((c) => mem.checklist.set(checklistKey(c.documentId, c.stepId), c));
  reminders.forEach((r) => mem.reminders.set(r.id, r));
  meta.forEach((m) => mem.meta.set(m.key, m.value));
}

async function flushToIdb(): Promise<void> {
  for (const m of mem.members.values()) await put('members', m);
  for (const d of mem.documents.values()) await put('documents', d);
  for (const p of mem.pages.values()) await put('pages', p);
  for (const c of mem.checklist.values()) await put('checklist_state', c);
  for (const r of mem.reminders.values()) await put('reminders', r);
  for (const [key, value] of mem.meta) await put('meta', { key, value });
}

function clearMemory(): void {
  Object.values(mem).forEach((m) => m.clear());
}

/** Apply the user's web persistence settings (called by StorageProvider on every change). */
export async function configureVault(config: VaultConfig): Promise<void> {
  const wantIdb = config.persist === 'indexeddb' && indexedDbAvailable();
  if (wantIdb && !persistent) {
    persistent = true;
    files.setBlobSink(idbBlobSink);
    try {
      await loadFromIdb();
      await flushToIdb();
    } catch {
      persistent = false;
      files.setBlobSink(null);
    }
  } else if (!wantIdb && persistent) {
    persistent = false;
    files.setBlobSink(null);
    await deleteIdb();
  }
  const g = globalThis as { addEventListener?: (e: string, f: () => void) => void; removeEventListener?: (e: string, f: () => void) => void };
  if (pagehideListener && g.removeEventListener) g.removeEventListener('pagehide', pagehideListener);
  pagehideListener = null;
  if (config.clearOnClose && persistent && g.addEventListener) {
    pagehideListener = () => {
      void vault.wipeAll();
    };
    g.addEventListener('pagehide', pagehideListener);
  }
}

export function isPersistent(): boolean {
  return persistent;
}

/** No scheduled notifications on web (reminders use .ics). */
export async function cancelAllNotifications(): Promise<void> {}

function ensureMe(): void {
  if (!mem.members.has(ME_MEMBER_ID)) {
    const me: Member = { id: ME_MEMBER_ID, name: '', color: '#0B4F8A', createdAt: new Date().toISOString() };
    mem.members.set(me.id, me);
    void put('members', me);
  }
}

function toRow(doc: StoredDocument): DocumentRow {
  const { analysis: _a, keepPages: _k, ...row } = doc;
  return row;
}

async function removeDocument(id: string): Promise<void> {
  mem.documents.delete(id);
  await del('documents', id);
  for (const [k, p] of [...mem.pages]) {
    if (p.documentId === id) {
      mem.pages.delete(k);
      await del('pages', [p.documentId, p.page]);
    }
  }
  for (const [k, c] of [...mem.checklist]) {
    if (c.documentId === id) {
      mem.checklist.delete(k);
      await del('checklist_state', [c.documentId, c.stepId]);
    }
  }
  for (const [k, r] of [...mem.reminders]) {
    if (r.documentId === id) {
      mem.reminders.delete(k);
      await del('reminders', r.id);
    }
  }
  mem.meta.delete(`chat:${id}`);
  await del('meta', `chat:${id}`);
  await files.deleteDocumentFiles(id);
}

let reminderSeq = 0;

export const vault: Vault = {
  async init() {},
  members: {
    async list() {
      return [...mem.members.values()].sort((a, b) => (a.createdAt < b.createdAt ? -1 : 1));
    },
    async add({ name, color }) {
      const m: Member = {
        id: `mem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        name: name.slice(0, 40),
        color,
        createdAt: new Date().toISOString(),
      };
      mem.members.set(m.id, m);
      await put('members', m);
      return m;
    },
    async rename(id, name) {
      const m = mem.members.get(id);
      if (!m) return;
      const next = { ...m, name: name.slice(0, 40) };
      mem.members.set(id, next);
      await put('members', next);
    },
    async remove(id, wipeDocuments) {
      if (id === ME_MEMBER_ID) return;
      const docs = [...mem.documents.values()].filter((d) => d.memberId === id);
      if (wipeDocuments) {
        for (const d of docs) await removeDocument(d.id);
      } else {
        ensureMe();
        for (const d of docs) {
          const moved = { ...d, memberId: ME_MEMBER_ID };
          mem.documents.set(d.id, moved);
          await put('documents', moved);
        }
      }
      mem.members.delete(id);
      await del('members', id);
    },
  },
  documents: {
    async list(memberId) {
      return [...mem.documents.values()]
        .filter((d) => !memberId || d.memberId === memberId)
        .sort(byCreatedDesc)
        .map(toRow);
    },
    async get(id) {
      return mem.documents.get(id) ?? null;
    },
    async save(doc, pages) {
      if (doc.memberId === ME_MEMBER_ID) ensureMe();
      mem.documents.set(doc.id, doc);
      await put('documents', doc);
      for (const [k, p] of [...mem.pages]) {
        if (p.documentId === doc.id) mem.pages.delete(k);
      }
      if (doc.keepPages) {
        for (const p of pages) {
          const w = await files.writePageFiles(doc.id, p.page, p.base64Jpeg, p.thumbBase64);
          const stored: StoredPage = { documentId: doc.id, page: p.page, filePath: w.filePath, thumbPath: w.thumbPath };
          mem.pages.set(pageKey(doc.id, p.page), stored);
          await put('pages', stored);
        }
      }
    },
    async move(id, memberId) {
      const d = mem.documents.get(id);
      if (!d) return;
      if (memberId === ME_MEMBER_ID) ensureMe();
      const next = { ...d, memberId };
      mem.documents.set(id, next);
      await put('documents', next);
    },
    remove: (id) => removeDocument(id),
    async search(q) {
      return [...mem.documents.values()]
        .filter((d) => documentMatches(d, q))
        .sort(byCreatedDesc)
        .map(toRow);
    },
  },
  pages: {
    async list(documentId) {
      return [...mem.pages.values()].filter((p) => p.documentId === documentId).sort((a, b) => a.page - b.page);
    },
    uri: (page) => files.fileUri(page.filePath),
  },
  checklist: {
    async get(documentId) {
      const out: Record<string, boolean> = {};
      for (const c of mem.checklist.values()) if (c.documentId === documentId) out[c.stepId] = c.checked;
      return out;
    },
    async set(documentId, stepId, checked) {
      const rec = { documentId, stepId, checked };
      mem.checklist.set(checklistKey(documentId, stepId), rec);
      await put('checklist_state', rec);
    },
  },
  reminders: {
    async list() {
      return [...mem.reminders.values()].sort((a, b) => (a.fireAt < b.fireAt ? -1 : a.fireAt > b.fireAt ? 1 : 0));
    },
    async add(r) {
      reminderSeq += 1;
      const rem: Reminder = { ...r, id: `rem_${Date.now().toString(36)}_${reminderSeq}` };
      mem.reminders.set(rem.id, rem);
      await put('reminders', rem);
      return rem;
    },
    async remove(id) {
      mem.reminders.delete(id);
      await del('reminders', id);
    },
    async setEnabled(id, on) {
      const r = mem.reminders.get(id);
      if (!r) return;
      const next = { ...r, enabled: on };
      mem.reminders.set(id, next);
      await put('reminders', next);
    },
  },
  consent: {
    get: () => consentStore.get(),
    set: (r) => consentStore.set(r),
    clear: () => consentStore.clear(),
  },
  async wipeAll() {
    clearMemory();
    await files.deleteAllFiles();
    if (persistent || indexedDbAvailable()) await deleteIdb();
  },
};
