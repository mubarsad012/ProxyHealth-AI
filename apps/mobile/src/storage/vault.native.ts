// Native vault (D-22, PRODUCT_SPEC §9.2): expo-sqlite `proxyhealth.db` (WAL, migrations via
// PRAGMA user_version) + page JPEGs under `Paths.document/vault/<doc_id>/`. Opened lazily on first
// use. Verified against https://docs.expo.dev/versions/v57.0.0/sdk/sqlite/ : openDatabaseAsync,
// execAsync, runAsync, getAllAsync, getFirstAsync, withTransactionAsync, closeAsync,
// deleteDatabaseAsync. Consent is NOT a table: `vault.consent` wraps `kv` (D-22).

import * as SQLite from 'expo-sqlite';

import type { DocumentRow, Member, Reminder, StoredDocument, StoredPage, Vault } from '@/storage/index';
import { consentStore } from '@/storage/consent';
import * as files from '@/storage/files.native';
import { DB_NAME, migrate } from '@/storage/migrations';
import {
  type DocumentDbRow,
  documentMatches,
  documentParams,
  documentRowFromDb,
  ME_MEMBER_ID,
  type MemberDbRow,
  memberFromRow,
  type PageDbRow,
  pageFromRow,
  type ReminderDbRow,
  reminderFromRow,
  reminderParams,
  storedDocumentFromDb,
} from '@/storage/rows';

type Db = SQLite.SQLiteDatabase;

export type VaultConfig = { persist: 'session' | 'indexeddb'; clearOnClose: boolean };

/** Web-only option; accepted and ignored on native so callers need no platform branch. */
export function configureVault(_config: VaultConfig): void {}

let dbPromise: Promise<Db> | null = null;

async function db(): Promise<Db> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const d = await SQLite.openDatabaseAsync(DB_NAME);
      await migrate(d);
      return d;
    })();
    dbPromise.catch(() => {
      dbPromise = null;
    });
  }
  return dbPromise;
}

type NotificationsModule = typeof import('expo-notifications');

/** Loaded on first use: importing expo-notifications registers push-token listeners (and warns in
 *  Expo Go), which the vault must not trigger at app start. */
function notifications(): NotificationsModule | null {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require('expo-notifications') as NotificationsModule;
  } catch {
    return null;
  }
}

function newReminderId(): string {
  return `rem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

async function cancelNotification(id: string | null): Promise<void> {
  if (!id) return;
  try {
    await notifications()?.cancelScheduledNotificationAsync(id);
  } catch {
    // already fired or never scheduled
  }
}

/** Cancel every scheduled local notification (first step of "Delete everything"). */
export async function cancelAllNotifications(): Promise<void> {
  try {
    await notifications()?.cancelAllScheduledNotificationsAsync();
  } catch {
    // notifications unavailable (Expo Go / permissions); nothing scheduled
  }
}

async function ensureMe(d: Db): Promise<void> {
  const existing = await d.getFirstAsync<MemberDbRow>('SELECT * FROM members WHERE id = ?', ME_MEMBER_ID);
  if (!existing) {
    await d.runAsync(
      'INSERT INTO members (id, name, color, created_at) VALUES (?, ?, ?, ?)',
      ME_MEMBER_ID,
      '',
      '#0B4F8A',
      new Date().toISOString(),
    );
  }
}

async function removeDocument(d: Db, id: string): Promise<void> {
  const rems = await d.getAllAsync<ReminderDbRow>('SELECT * FROM reminders WHERE document_id = ?', id);
  for (const r of rems) await cancelNotification(r.notification_id);
  await d.withTransactionAsync(async () => {
    await d.runAsync('DELETE FROM documents WHERE id = ?', id);
    await d.runAsync('DELETE FROM pages WHERE document_id = ?', id);
    await d.runAsync('DELETE FROM checklist_state WHERE document_id = ?', id);
    await d.runAsync('DELETE FROM reminders WHERE document_id = ?', id);
    await d.runAsync('DELETE FROM meta WHERE key = ?', `chat:${id}`);
  });
  await files.deleteDocumentFiles(id);
}

export const vault: Vault = {
  async init() {
    await db();
  },
  members: {
    async list(): Promise<Member[]> {
      const rows = await (await db()).getAllAsync<MemberDbRow>('SELECT * FROM members ORDER BY created_at ASC');
      return rows.map(memberFromRow);
    },
    async add({ name, color }): Promise<Member> {
      const d = await db();
      const member: Member = {
        id: `mem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        name: name.slice(0, 40),
        color,
        createdAt: new Date().toISOString(),
      };
      await d.runAsync(
        'INSERT INTO members (id, name, color, created_at) VALUES (?, ?, ?, ?)',
        member.id,
        member.name,
        member.color,
        member.createdAt,
      );
      return member;
    },
    async rename(id, name) {
      await (await db()).runAsync('UPDATE members SET name = ? WHERE id = ?', name.slice(0, 40), id);
    },
    async remove(id, wipeDocuments) {
      if (id === ME_MEMBER_ID) return; // "Me" cannot be deleted (PRODUCT_SPEC §9.2)
      const d = await db();
      if (wipeDocuments) {
        const docs = await d.getAllAsync<{ id: string }>('SELECT id FROM documents WHERE member_id = ?', id);
        for (const doc of docs) await removeDocument(d, doc.id);
      } else {
        await ensureMe(d);
        await d.runAsync('UPDATE documents SET member_id = ? WHERE member_id = ?', ME_MEMBER_ID, id);
      }
      await d.runAsync('DELETE FROM members WHERE id = ?', id);
    },
  },
  documents: {
    async list(memberId?: string): Promise<DocumentRow[]> {
      const d = await db();
      const rows = memberId
        ? await d.getAllAsync<DocumentDbRow>(
            'SELECT * FROM documents WHERE member_id = ? ORDER BY created_at DESC',
            memberId,
          )
        : await d.getAllAsync<DocumentDbRow>('SELECT * FROM documents ORDER BY created_at DESC');
      return rows.map(documentRowFromDb);
    },
    async get(id): Promise<StoredDocument | null> {
      const row = await (await db()).getFirstAsync<DocumentDbRow>('SELECT * FROM documents WHERE id = ?', id);
      return row ? storedDocumentFromDb(row) : null;
    },
    async save(doc, pages) {
      const d = await db();
      if (doc.memberId === ME_MEMBER_ID) await ensureMe(d);
      const written: StoredPage[] = [];
      if (doc.keepPages) {
        for (const p of pages) {
          const w = await files.writePageFiles(doc.id, p.page, p.base64Jpeg, p.thumbBase64);
          written.push({ documentId: doc.id, page: p.page, filePath: w.filePath, thumbPath: w.thumbPath });
        }
      }
      await d.withTransactionAsync(async () => {
        await d.runAsync(
          `INSERT OR REPLACE INTO documents (id, member_id, title, category, document_type, analysis_json,
            created_at, next_date_iso, keep_pages, page_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          ...documentParams(doc),
        );
        await d.runAsync('DELETE FROM pages WHERE document_id = ?', doc.id);
        for (const p of written) {
          await d.runAsync(
            'INSERT INTO pages (document_id, page, file_path, thumb_path) VALUES (?, ?, ?, ?)',
            p.documentId,
            p.page,
            p.filePath,
            p.thumbPath,
          );
        }
      });
    },
    async move(id, memberId) {
      const d = await db();
      if (memberId === ME_MEMBER_ID) await ensureMe(d);
      await d.runAsync('UPDATE documents SET member_id = ? WHERE id = ?', memberId, id);
    },
    async remove(id) {
      await removeDocument(await db(), id);
    },
    async search(q) {
      const d = await db();
      const rows = await d.getAllAsync<DocumentDbRow>('SELECT * FROM documents ORDER BY created_at DESC');
      return rows
        .map(storedDocumentFromDb)
        .filter((doc) => documentMatches(doc, q))
        .map(({ analysis: _a, keepPages: _k, ...row }) => row);
    },
  },
  pages: {
    async list(documentId) {
      const rows = await (await db()).getAllAsync<PageDbRow>(
        'SELECT * FROM pages WHERE document_id = ? ORDER BY page ASC',
        documentId,
      );
      return rows.map(pageFromRow);
    },
    uri: (page) => files.fileUri(page.filePath),
  },
  checklist: {
    async get(documentId) {
      const rows = await (await db()).getAllAsync<{ step_id: string; checked: number }>(
        'SELECT step_id, checked FROM checklist_state WHERE document_id = ?',
        documentId,
      );
      const out: Record<string, boolean> = {};
      for (const r of rows) out[r.step_id] = r.checked === 1;
      return out;
    },
    async set(documentId, stepId, checked) {
      await (await db()).runAsync(
        'INSERT OR REPLACE INTO checklist_state (document_id, step_id, checked) VALUES (?, ?, ?)',
        documentId,
        stepId,
        checked ? 1 : 0,
      );
    },
  },
  reminders: {
    async list(): Promise<Reminder[]> {
      const rows = await (await db()).getAllAsync<ReminderDbRow>('SELECT * FROM reminders ORDER BY fire_at ASC');
      return rows.map(reminderFromRow);
    },
    async add(r): Promise<Reminder> {
      const reminder: Reminder = { ...r, id: newReminderId() };
      await (await db()).runAsync(
        `INSERT INTO reminders (id, document_id, demand_id, fire_at, notification_id, detail_opt_in, enabled, label)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        ...reminderParams(reminder),
      );
      return reminder;
    },
    async remove(id) {
      const d = await db();
      const row = await d.getFirstAsync<ReminderDbRow>('SELECT * FROM reminders WHERE id = ?', id);
      if (row) await cancelNotification(row.notification_id);
      await d.runAsync('DELETE FROM reminders WHERE id = ?', id);
    },
    async setEnabled(id, on) {
      await (await db()).runAsync('UPDATE reminders SET enabled = ? WHERE id = ?', on ? 1 : 0, id);
    },
  },
  consent: {
    get: () => consentStore.get(),
    set: (r) => consentStore.set(r),
    clear: () => consentStore.clear(),
  },
  /** Vault data only (files, DB). `storage/wipe.ts` adds notifications, secure store, kv, install id. */
  async wipeAll() {
    await files.deleteAllFiles();
    const open = dbPromise;
    dbPromise = null;
    if (open) {
      try {
        await (await open).closeAsync();
      } catch {
        // already closed
      }
    }
    try {
      await SQLite.deleteDatabaseAsync(DB_NAME);
    } catch {
      // no database yet
    }
  },
};

/** Test hook: forget the open handle. */
export function resetNativeVaultForTests(): void {
  dbPromise = null;
}
