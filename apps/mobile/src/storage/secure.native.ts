// Device-only secrets (D-22): a random 256-bit `vault_key` in expo-secure-store with
// WHEN_UNLOCKED_THIS_DEVICE_ONLY, used in v1 only to derive the PIN verifier (SHOULD). No app-layer
// encryption is claimed. Verified against https://docs.expo.dev/versions/v57.0.0/sdk/securestore/
// and the installed types: setItemAsync/getItemAsync/deleteItemAsync(key, { keychainAccessible }).
// expo-crypto: getRandomBytes(n), digestStringAsync(SHA256, s).

import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';

const OPTS: SecureStore.SecureStoreOptions = {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export const SECURE_KEYS = {
  vaultKey: 'ph_vault_key',
  pinVerifier: 'ph_pin_verifier',
  pinSalt: 'ph_pin_salt',
} as const;

function toHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

export const secureAvailable = true;

export async function getOrCreateVaultKey(): Promise<string> {
  const existing = await SecureStore.getItemAsync(SECURE_KEYS.vaultKey, OPTS);
  if (existing) return existing;
  const key = toHex(Crypto.getRandomBytes(32));
  await SecureStore.setItemAsync(SECURE_KEYS.vaultKey, key, OPTS);
  return key;
}

async function verifierFor(pin: string, salt: string): Promise<string> {
  const vaultKey = await getOrCreateVaultKey();
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, `${salt}:${vaultKey}:${pin}`);
}

/** PIN lock (SHOULD): store only a salted verifier, never the PIN. */
export async function setPin(pin: string): Promise<void> {
  const salt = toHex(Crypto.getRandomBytes(16));
  await SecureStore.setItemAsync(SECURE_KEYS.pinSalt, salt, OPTS);
  await SecureStore.setItemAsync(SECURE_KEYS.pinVerifier, await verifierFor(pin, salt), OPTS);
}

export async function checkPin(pin: string): Promise<boolean> {
  const salt = await SecureStore.getItemAsync(SECURE_KEYS.pinSalt, OPTS);
  const stored = await SecureStore.getItemAsync(SECURE_KEYS.pinVerifier, OPTS);
  if (!salt || !stored) return false;
  return (await verifierFor(pin, salt)) === stored;
}

export async function hasPin(): Promise<boolean> {
  return Boolean(await SecureStore.getItemAsync(SECURE_KEYS.pinVerifier, OPTS));
}

export async function clearPin(): Promise<void> {
  await SecureStore.deleteItemAsync(SECURE_KEYS.pinVerifier, OPTS);
  await SecureStore.deleteItemAsync(SECURE_KEYS.pinSalt, OPTS);
}

/** Part of "Delete everything". */
export async function clearSecure(): Promise<void> {
  for (const key of Object.values(SECURE_KEYS)) {
    try {
      await SecureStore.deleteItemAsync(key, OPTS);
    } catch {
      // missing keys are fine
    }
  }
}
