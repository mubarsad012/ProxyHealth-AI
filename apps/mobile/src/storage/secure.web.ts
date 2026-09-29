// Web secure-store shim (D-23): expo-secure-store has no web implementation and the web build keeps
// no secrets. No vault key, no PIN lock on web; every call is a harmless no-op so shared code needs
// no platform branch.

export const SECURE_KEYS = {
  vaultKey: 'ph_vault_key',
  pinVerifier: 'ph_pin_verifier',
  pinSalt: 'ph_pin_salt',
} as const;

/** PIN lock and the vault key are unavailable on web. */
export const secureAvailable = false;

export async function getOrCreateVaultKey(): Promise<string> {
  throw new Error('No secure storage on web');
}

export async function setPin(_pin: string): Promise<void> {
  throw new Error('PIN lock is not available on web');
}

export async function checkPin(_pin: string): Promise<boolean> {
  return false;
}

export async function hasPin(): Promise<boolean> {
  return false;
}

export async function clearPin(): Promise<void> {}

export async function clearSecure(): Promise<void> {}
