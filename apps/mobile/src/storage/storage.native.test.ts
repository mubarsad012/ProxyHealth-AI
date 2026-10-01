// Native vault with mocked expo-sqlite / expo-file-system / expo-notifications / expo-secure-store
// (BUILD_PLAN §5.5 step 4): the SQL migration list, row mapping, the save path, and the call order
// of `vault.wipeAll()` and "Delete everything". Platform files are imported explicitly.

import type { AnalysisResult } from '@/api/types';
import { CAPTURE_CACHE_DIRS, purgeCaptureCache } from '@/storage/cache.native';
import type { StoredDocument } from '@/storage/index';
import { kv, KV_KEYS } from '@/storage/kv';
import { DB_NAME, LATEST_VERSION, migrate, type MigratableDb, MIGRATIONS, pendingMigrations } from '@/storage/migrations';
import { type DocumentDbRow, documentRowFromDb, reminderFromRow, storedDocumentFromDb } from '@/storage/rows';
import { resetNativeVaultForTests, vault } from '@/storage/vault.native';
import { wipeEverything } from '@/storage/wipe';
// (jest.mock calls below are hoisted above these imports by babel-jest.)

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const mockCalls: string[] = [];
let mockUserVersion = 0;
let mockFirstRow: unknown = null;
let mockAllRows: unknown[] = [];

const mockDb = {
  execAsync: jest.fn(async (sql: string) => {
    mockCalls.push(`exec:${sql}`);
  }),
  getFirstAsync: jest.fn(async (sql: string) => {
    mockCalls.push(`first:${sql}`);
    if (sql.startsWith('PRAGMA user_version')) return { user_version: mockUserVersion };
    return mockFirstRow;
  }),
  getAllAsync: jest.fn(async (sql: string) => {
    mockCalls.push(`all:${sql}`);
    return mockAllRows;
  }),
  runAsync: jest.fn(async (sql: string) => {
    mockCalls.push(`run:${sql.replace(/\s+/g, ' ').trim()}`);
    return { lastInsertRowId: 1, changes: 1 };
  }),
  withTransactionAsync: jest.fn(async (task: () => Promise<void>) => {
    mockCalls.push('tx:begin');
    await task();
    mockCalls.push('tx:end');
  }),
  closeAsync: jest.fn(async () => {
    mockCalls.push('close');
  }),
};

jest.mock('expo-sqlite', () => ({
  openDatabaseAsync: jest.fn(async (name: string) => {
    mockCalls.push(`open:${name}`);
    return mockDb;
  }),
  deleteDatabaseAsync: jest.fn(async (name: string) => {
    mockCalls.push(`deleteDatabase:${name}`);
  }),
}));

jest.mock('expo-file-system', () => {
  const join = (parts: unknown[]) =>
    parts.map((p) => (typeof p === 'string' ? p : (p as { uri: string }).uri)).join('/');
  class Directory {
    uri: string;
    exists = true;
    constructor(...parts: unknown[]) {
      this.uri = join(parts);
    }
    create() {
      mockCalls.push(`mkdir:${this.uri}`);
    }
    delete() {
      mockCalls.push(`rmdir:${this.uri}`);
    }
  }
  class File {
    uri: string;
    exists = false;
    constructor(...parts: unknown[]) {
      this.uri = join(parts);
    }
    create() {
      mockCalls.push(`create:${this.uri}`);
    }
    write(_content: string, opts?: { encoding?: string }) {
      mockCalls.push(`write:${this.uri}:${opts?.encoding ?? 'utf8'}`);
    }
    delete() {
      mockCalls.push(`rm:${this.uri}`);
    }
  }
  return { Directory, File, Paths: { document: 'file:///doc', cache: 'file:///cache' } };
});

jest.mock('expo-notifications', () => ({
  cancelAllScheduledNotificationsAsync: jest.fn(async () => {
    mockCalls.push('notifications:cancelAll');
  }),
  cancelScheduledNotificationAsync: jest.fn(async (id: string) => {
    mockCalls.push(`notifications:cancel:${id}`);
  }),
}));

jest.mock('expo-secure-store', () => ({
  WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'WHEN_UNLOCKED_THIS_DEVICE_ONLY',
  getItemAsync: jest.fn(async () => null),
  setItemAsync: jest.fn(async () => undefined),
  deleteItemAsync: jest.fn(async (key: string) => {
    mockCalls.push(`secure:delete:${key}`);
  }),
}));

// `storage/wipe.ts` imports `@/storage/vault` and `@/storage/secure`; under the single jest-expo
// (iOS) preset those resolve to the same vault.native.ts / secure.native.ts modules imported here.

const dbRow: DocumentDbRow = {
  id: 'doc-1',
  member_id: 'me',
  title: 'Medicaid letter',
  category: 'benefits',
  document_type: 'medicaid_renewal',
  analysis_json: JSON.stringify({ analysis_id: 'doc-1', sender_as_written: 'DMAS' }),
  created_at: '2026-09-27T14:00:00Z',
  next_date_iso: '2026-10-14',
  keep_pages: 1,
  page_count: 2,
};

beforeEach(() => {
  mockCalls.length = 0;
  mockUserVersion = 0;
  mockFirstRow = null;
  mockAllRows = [];
  resetNativeVaultForTests();
});

describe('migrations', () => {
  it('version 1 creates exactly the six vault tables and no consent table (D-22)', () => {
    const sql = MIGRATIONS[0].statements.join('\n');
    for (const table of ['members', 'documents', 'pages', 'checklist_state', 'reminders', 'meta']) {
      expect(sql).toContain(`CREATE TABLE IF NOT EXISTS ${table} (`);
    }
    expect(sql).not.toMatch(/consent/i);
    expect(LATEST_VERSION).toBe(1);
    expect(pendingMigrations(1)).toEqual([]);
  });

  it('runs WAL + pending migrations and sets PRAGMA user_version', async () => {
    expect(await migrate(mockDb as unknown as MigratableDb)).toBe(1);
    expect(mockCalls[0]).toBe('exec:PRAGMA journal_mode = WAL');
    expect(mockCalls[2]).toMatch(/PRAGMA user_version = 1$/);
    mockCalls.length = 0;
    mockUserVersion = 1;
    await migrate(mockDb as unknown as MigratableDb);
    expect(mockCalls.filter((c) => c.startsWith('exec:'))).toEqual(['exec:PRAGMA journal_mode = WAL']);
  });
});

describe('row mapping', () => {
  it('maps document rows and parses analysis_json (null for read-later rows)', () => {
    expect(documentRowFromDb(dbRow)).toEqual({
      id: 'doc-1',
      memberId: 'me',
      title: 'Medicaid letter',
      category: 'benefits',
      documentType: 'medicaid_renewal',
      createdAt: '2026-09-27T14:00:00Z',
      nextDateIso: '2026-10-14',
      pageCount: 2,
    });
    const stored = storedDocumentFromDb(dbRow);
    expect(stored.keepPages).toBe(true);
    expect(stored.analysis.sender_as_written).toBe('DMAS');
    expect(storedDocumentFromDb({ ...dbRow, analysis_json: null }).analysis).toBeNull();
  });

  it('maps reminder rows', () => {
    expect(
      reminderFromRow({
        id: 'r1',
        document_id: 'doc-1',
        demand_id: 'd1',
        fire_at: '2026-10-07T13:00:00Z',
        notification_id: 'n1',
        detail_opt_in: 0,
        enabled: 1,
        label: 'Answer by',
      }),
    ).toEqual({
      id: 'r1',
      documentId: 'doc-1',
      demandId: 'd1',
      fireAt: '2026-10-07T13:00:00Z',
      notificationId: 'n1',
      detailOptIn: false,
      enabled: true,
      label: 'Answer by',
    });
  });
});

describe('native vault', () => {
  it('opens proxyhealth.db lazily and migrates once', async () => {
    await vault.init();
    await vault.init();
    expect(mockCalls.filter((c) => c.startsWith('open:'))).toEqual([`open:${DB_NAME}`]);
  });

  it('get() maps the stored row', async () => {
    mockFirstRow = dbRow;
    const doc = await vault.documents.get('doc-1');
    expect(doc?.title).toBe('Medicaid letter');
    expect(doc?.memberId).toBe('me');
  });

  it('save() writes page JPEGs as base64 files, then rows in one transaction', async () => {
    const doc: StoredDocument = {
      ...storedDocumentFromDb(dbRow),
      analysis: { analysis_id: 'doc-1' } as AnalysisResult,
      memberId: 'mem-2',
    };
    await vault.documents.save(doc, [{ page: 1, base64Jpeg: 'AAAA', thumbBase64: 'BBBB' }]);
    const writes = mockCalls.filter((c) => c.startsWith('write:'));
    expect(writes).toEqual([
      'write:file:///doc/vault/doc-1/page-1.jpg:base64',
      'write:file:///doc/vault/doc-1/thumb-1.jpg:base64',
    ]);
    const tx = mockCalls.slice(mockCalls.indexOf('tx:begin'), mockCalls.indexOf('tx:end') + 1);
    expect(tx[1]).toMatch(/^run:INSERT OR REPLACE INTO documents/);
    expect(tx.some((c) => c.startsWith('run:INSERT INTO pages'))).toBe(true);
    expect(mockCalls.indexOf(writes[0])).toBeLessThan(mockCalls.indexOf('tx:begin'));
  });

  it('remove() cancels the paper\'s reminders and deletes rows, chat history and files', async () => {
    mockAllRows = [{ id: 'r1', document_id: 'doc-1', notification_id: 'n1' }];
    await vault.documents.remove('doc-1');
    expect(mockCalls).toContain('notifications:cancel:n1');
    expect(mockCalls).toContain('run:DELETE FROM meta WHERE key = ?');
    expect(mockCalls[mockCalls.length - 1]).toBe('rmdir:file:///doc/vault/doc-1');
  });

  it('wipeAll(): files first, then close, then delete the database', async () => {
    await vault.init();
    mockCalls.length = 0;
    await vault.wipeAll();
    expect(mockCalls).toEqual(['rmdir:file:///doc/vault', 'close', `deleteDatabase:${DB_NAME}`]);
  });
});

describe('Delete everything (storage/wipe.ts)', () => {
  it('runs every step in the COMPLIANCE_PRIVACY §9.5 order and leaves kv empty', async () => {
    await kv.setJSON(KV_KEYS.consent, { consent_version: 'x' });
    await kv.set(KV_KEYS.installId, 'install-1');
    await vault.init();
    mockCalls.length = 0;
    const steps = await wipeEverything();
    expect(steps).toEqual(['notifications', 'hooks', 'vault', 'cache', 'secure', 'settings', 'kv', 'install_id', 'memory']);
    const order = [
      'notifications:cancelAll',
      'rmdir:file:///doc/vault',
      `deleteDatabase:${DB_NAME}`,
      'rmdir:file:///cache/Camera',
      'secure:delete:ph_vault_key',
    ];
    const idx = order.map((c) => mockCalls.indexOf(c));
    expect(idx.every((i) => i >= 0)).toBe(true);
    expect([...idx].sort((a, b) => a - b)).toEqual(idx);
    expect(await kv.get(KV_KEYS.consent)).toBeNull();
    expect(await kv.get(KV_KEYS.installId)).toBeNull();
    // Unsaved full-size photos, crops, picked PDFs and printed sheets go too (D-22).
    for (const dir of ['Camera', 'ImageManipulator', 'ImagePicker', 'DocumentPicker', 'Print']) {
      expect(mockCalls).toContain(`rmdir:file:///cache/${dir}`);
    }
  });
});

describe('capture cache (storage/cache.native.ts)', () => {
  it('purgeCaptureCache deletes only the capture folders under Paths.cache, never the vault', async () => {
    mockCalls.length = 0;
    await purgeCaptureCache();
    expect(mockCalls).toEqual(CAPTURE_CACHE_DIRS.map((d) => `rmdir:file:///cache/${d}`));
    expect(CAPTURE_CACHE_DIRS).toEqual(['Camera', 'ImageManipulator', 'ImagePicker', 'DocumentPicker', 'Print']);
  });
});
