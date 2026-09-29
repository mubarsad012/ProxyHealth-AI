// Type declaration for the platform-resolved vault module. Metro picks `vault.native.ts` on
// iOS/Android and `vault.web.ts` on web (ARCHITECTURE §3.1); TypeScript resolves `./vault` to this
// file. Both implementations export exactly these names.

import type { Vault } from '@/storage/index';

export type VaultConfig = { persist: 'session' | 'indexeddb'; clearOnClose: boolean };

export declare const vault: Vault;

/** Web: switch memory ⇄ IndexedDB and arm "clear on close". Native: no-op. */
export declare function configureVault(config: VaultConfig): void | Promise<void>;

/** Native: cancel every scheduled local notification. Web: no-op. */
export declare function cancelAllNotifications(): Promise<void>;
