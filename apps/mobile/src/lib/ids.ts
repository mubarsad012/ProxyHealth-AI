// Ids (D-08): a random install id (UUID v4) sent as `X-Install-Id`, HMAC-hashed server-side; new
// request ids per call. expo-crypto works on every platform. CL-010: the install id is generated
// lazily on first API use — i.e. at consent, not at first launch.

import * as Crypto from 'expo-crypto';

import { kv, KV_KEYS } from '@/storage/kv';

export function newId(): string {
  try {
    return Crypto.randomUUID();
  } catch {
    // Extremely unlikely; keep the app usable rather than crash.
    return `${Date.now().toString(16)}-${Math.random().toString(16).slice(2, 10)}`;
  }
}

export const newRequestId = newId;

let installIdPromise: Promise<string> | null = null;

export function getInstallId(): Promise<string> {
  if (!installIdPromise) {
    installIdPromise = (async () => {
      const existing = await kv.get(KV_KEYS.installId);
      if (existing) return existing;
      const id = newId();
      await kv.set(KV_KEYS.installId, id);
      return id;
    })();
  }
  return installIdPromise;
}

/** Settings → developer "New device id", and part of "Delete everything". */
export async function rotateInstallId(): Promise<string> {
  const id = newId();
  await kv.set(KV_KEYS.installId, id);
  installIdPromise = Promise.resolve(id);
  return id;
}

export async function clearInstallId(): Promise<void> {
  await kv.remove(KV_KEYS.installId);
  installIdPromise = null;
}

/** Local document / page ids. */
export function newDocumentId(): string {
  return `doc_${newId()}`;
}

export function newPageId(): string {
  return `page_${newId()}`;
}
