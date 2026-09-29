// Thin IndexedDB wrapper for the web vault opt-in (D-23: no sqlite-wasm, no COOP/COEP headers).
// Database `proxyhealth`, object stores mirroring the sqlite tables plus `blobs` for page images.
// Only used after the user chose "Keep on this device (not encrypted by the app)". fake-indexeddb
// is not installed, so this path is verified manually (BUILD_PLAN §1.1, §6).

import { WEB_DB_NAME, WEB_DB_VERSION, WEB_STORES } from '@/storage/migrations';

export type StoreName = keyof typeof WEB_STORES;

export function indexedDbAvailable(): boolean {
  return typeof globalThis !== 'undefined' && typeof (globalThis as { indexedDB?: unknown }).indexedDB === 'object';
}

function req<T>(r: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

let dbPromise: Promise<IDBDatabase> | null = null;

export function openIdb(): Promise<IDBDatabase> {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const open = indexedDB.open(WEB_DB_NAME, WEB_DB_VERSION);
      open.onupgradeneeded = () => {
        const d = open.result;
        for (const [name, def] of Object.entries(WEB_STORES)) {
          if (!d.objectStoreNames.contains(name)) {
            d.createObjectStore(name, { keyPath: def.keyPath as string | string[] });
          }
        }
      };
      open.onsuccess = () => resolve(open.result);
      open.onerror = () => reject(open.error);
    });
    dbPromise.catch(() => {
      dbPromise = null;
    });
  }
  return dbPromise;
}

export async function idbAll<T>(store: StoreName): Promise<T[]> {
  const d = await openIdb();
  return req(d.transaction(store, 'readonly').objectStore(store).getAll() as IDBRequest<T[]>);
}

export async function idbGet<T>(store: StoreName, key: IDBValidKey): Promise<T | null> {
  const d = await openIdb();
  const v = await req(d.transaction(store, 'readonly').objectStore(store).get(key) as IDBRequest<T | undefined>);
  return v ?? null;
}

export async function idbPut(store: StoreName, value: unknown): Promise<void> {
  const d = await openIdb();
  await req(d.transaction(store, 'readwrite').objectStore(store).put(value));
}

export async function idbDelete(store: StoreName, key: IDBValidKey): Promise<void> {
  const d = await openIdb();
  await req(d.transaction(store, 'readwrite').objectStore(store).delete(key));
}

/** Delete every record whose string key starts with `prefix` (blobs by document). */
export async function idbDeletePrefix(store: StoreName, prefix: string): Promise<void> {
  const d = await openIdb();
  const keys = await req(d.transaction(store, 'readonly').objectStore(store).getAllKeys());
  const tx = d.transaction(store, 'readwrite').objectStore(store);
  await Promise.all(
    keys.filter((k) => typeof k === 'string' && k.startsWith(prefix)).map((k) => req(tx.delete(k))),
  );
}

/** Remove the whole `proxyhealth` database ("Delete everything", clear-on-close, opt-out). */
export async function deleteIdb(): Promise<void> {
  if (!indexedDbAvailable()) return;
  const open = dbPromise;
  dbPromise = null;
  if (open) {
    try {
      (await open).close();
    } catch {
      // already closed
    }
  }
  await new Promise<void>((resolve) => {
    const r = indexedDB.deleteDatabase(WEB_DB_NAME);
    r.onsuccess = () => resolve();
    r.onerror = () => resolve();
    r.onblocked = () => resolve();
  });
}
