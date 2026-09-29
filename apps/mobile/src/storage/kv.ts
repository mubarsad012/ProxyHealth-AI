// AsyncStorage wrapper for small preferences (D-22): settings, consent record, install id, pack
// cache index, server-config cache. Works on every platform (web = localStorage). Nothing
// sensitive is stored here; the vault holds documents.

import AsyncStorage from '@react-native-async-storage/async-storage';

const PREFIX = 'ph:';

export const KV_KEYS = {
  settings: `${PREFIX}settings`,
  consent: `${PREFIX}consent`,
  consentDecision: `${PREFIX}consent_decision`,
  installId: `${PREFIX}install_id`,
  serverConfig: `${PREFIX}server_config`,
  packIndex: `${PREFIX}packs:index`,
  packPrefix: `${PREFIX}pack:`,
  missingKeys: `${PREFIX}i18n:missing`,
  webVaultOptIn: `${PREFIX}web_vault_opt_in`,
} as const;

/** In-memory fallback so the app never crashes when the storage backend is unavailable
 *  (private browsing, quota, or a test without the AsyncStorage mock). */
const memory = new Map<string, string>();

async function safe<T>(op: () => Promise<T>, fallback: () => T): Promise<T> {
  try {
    return await op();
  } catch {
    return fallback();
  }
}

export const kv = {
  async get(key: string): Promise<string | null> {
    return safe(
      async () => {
        const v = await AsyncStorage.getItem(key);
        return v ?? memory.get(key) ?? null;
      },
      () => memory.get(key) ?? null,
    );
  },
  async set(key: string, value: string): Promise<void> {
    memory.set(key, value);
    await safe(() => AsyncStorage.setItem(key, value), () => undefined);
  },
  async remove(key: string): Promise<void> {
    memory.delete(key);
    await safe(() => AsyncStorage.removeItem(key), () => undefined);
  },
  async getJSON<T>(key: string): Promise<T | null> {
    const raw = await kv.get(key);
    if (raw == null) return null;
    try {
      return JSON.parse(raw) as T;
    } catch {
      // Corrupted value: drop it silently (S0 "corrupted pack cache" rule).
      await kv.remove(key);
      return null;
    }
  },
  async setJSON(key: string, value: unknown): Promise<void> {
    await kv.set(key, JSON.stringify(value));
  },
  async keys(): Promise<string[]> {
    return safe(
      async () => {
        const all = await AsyncStorage.getAllKeys();
        const set = new Set<string>([...all, ...memory.keys()]);
        return [...set].filter((k) => k.startsWith(PREFIX));
      },
      () => [...memory.keys()],
    );
  },
  async removeByPrefix(prefix: string): Promise<void> {
    const keys = (await kv.keys()).filter((k) => k.startsWith(prefix));
    keys.forEach((k) => memory.delete(k));
    if (keys.length) await safe(() => AsyncStorage.multiRemove(keys), () => undefined);
  },
  /** Removes every ProxyHealth key (settings, consent, install id, pack cache, config cache). */
  async clearAll(): Promise<void> {
    const keys = await kv.keys();
    memory.clear();
    if (keys.length) await safe(() => AsyncStorage.multiRemove(keys), () => undefined);
  },
};

export type Kv = typeof kv;
