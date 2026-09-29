// Schema versions for the native sqlite vault (ARCHITECTURE §3.1 "Storage layer", PRODUCT_SPEC §9.2,
// D-22). Applied in order by `migrate()` using `PRAGMA user_version` (expo-sqlite docs, SDK 57).
// There is no consent table: the consent record lives in `kv` (D-22). Web mirrors these tables as
// IndexedDB object stores (`WEB_STORES`).

export interface Migration {
  version: number;
  statements: string[];
}

export const DB_NAME = 'proxyhealth.db';

export const MIGRATIONS: readonly Migration[] = [
  {
    version: 1,
    statements: [
      `CREATE TABLE IF NOT EXISTS members (
        id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        color TEXT NOT NULL,
        created_at TEXT NOT NULL
      )`,
      `CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY NOT NULL,
        member_id TEXT NOT NULL,
        title TEXT NOT NULL,
        category TEXT NOT NULL,
        document_type TEXT NOT NULL,
        analysis_json TEXT,
        created_at TEXT NOT NULL,
        next_date_iso TEXT,
        keep_pages INTEGER NOT NULL DEFAULT 0,
        page_count INTEGER NOT NULL DEFAULT 0
      )`,
      'CREATE INDEX IF NOT EXISTS documents_member ON documents (member_id)',
      `CREATE TABLE IF NOT EXISTS pages (
        document_id TEXT NOT NULL,
        page INTEGER NOT NULL,
        file_path TEXT NOT NULL,
        thumb_path TEXT,
        PRIMARY KEY (document_id, page)
      )`,
      `CREATE TABLE IF NOT EXISTS checklist_state (
        document_id TEXT NOT NULL,
        step_id TEXT NOT NULL,
        checked INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (document_id, step_id)
      )`,
      `CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY NOT NULL,
        document_id TEXT NOT NULL,
        demand_id TEXT NOT NULL,
        fire_at TEXT NOT NULL,
        notification_id TEXT,
        detail_opt_in INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 1,
        label TEXT NOT NULL DEFAULT ''
      )`,
      `CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY NOT NULL,
        value TEXT
      )`,
    ],
  },
];

export const LATEST_VERSION = MIGRATIONS[MIGRATIONS.length - 1].version;

/** The subset of `SQLiteDatabase` the migrator needs (keeps tests free of the native module). */
export interface MigratableDb {
  execAsync(source: string): Promise<void>;
  getFirstAsync<T>(source: string, ...params: unknown[]): Promise<T | null>;
}

/** Migrations newer than `current`, in order. */
export function pendingMigrations(current: number): Migration[] {
  return MIGRATIONS.filter((m) => m.version > current);
}

/** WAL + every pending migration + `PRAGMA user_version = N`. Returns the version reached. */
export async function migrate(db: MigratableDb): Promise<number> {
  await db.execAsync('PRAGMA journal_mode = WAL');
  const row = await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
  let current = row?.user_version ?? 0;
  for (const m of pendingMigrations(current)) {
    await db.execAsync(`${m.statements.join(';\n')};\nPRAGMA user_version = ${m.version}`);
    current = m.version;
  }
  return current;
}

/** Web (IndexedDB) object stores mirroring the tables; key paths match the sqlite primary keys. */
export const WEB_STORES = {
  members: { keyPath: 'id' },
  documents: { keyPath: 'id' },
  pages: { keyPath: ['documentId', 'page'] },
  checklist_state: { keyPath: ['documentId', 'stepId'] },
  reminders: { keyPath: 'id' },
  meta: { keyPath: 'key' },
  blobs: { keyPath: 'path' },
} as const;

export const WEB_DB_NAME = 'proxyhealth';
export const WEB_DB_VERSION = 1;
