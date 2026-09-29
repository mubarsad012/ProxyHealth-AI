// Type declaration for the platform-resolved secure module (`secure.native.ts` via expo-secure-store,
// `secure.web.ts` in-memory shim — D-22/D-23). TypeScript resolves `./secure` to this file.

export declare const SECURE_KEYS: {
  readonly vaultKey: 'ph_vault_key';
  readonly pinVerifier: 'ph_pin_verifier';
  readonly pinSalt: 'ph_pin_salt';
};

/** False on web: no vault key and no PIN lock there. */
export declare const secureAvailable: boolean;

export declare function getOrCreateVaultKey(): Promise<string>;
export declare function setPin(pin: string): Promise<void>;
export declare function checkPin(pin: string): Promise<boolean>;
export declare function hasPin(): Promise<boolean>;
export declare function clearPin(): Promise<void>;
export declare function clearSecure(): Promise<void>;
