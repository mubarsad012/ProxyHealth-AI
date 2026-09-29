// StorageProvider (ARCHITECTURE §3 `_layout.tsx` providers): exposes the platform vault and keeps the
// web persistence mode (session ⇄ IndexedDB, clear-on-close) in step with Settings (D-23). The
// native database opens lazily on first use, so nothing here blocks the first render.

import { createContext, type ReactNode, useContext, useEffect } from 'react';

import { configureVault, type Vault, vault } from '@/storage/index';
import { useSettings } from '@/store/settings';

const VaultContext = createContext<Vault>(vault);

export function useVault(): Vault {
  return useContext(VaultContext);
}

export function StorageProvider({ children, value }: { children: ReactNode; value?: Vault }) {
  const webPersist = useSettings((s) => s.webPersist);
  const clearOnClose = useSettings((s) => s.clearOnClose);
  const hydrated = useSettings((s) => s.hydrated);
  useEffect(() => {
    if (!hydrated) return;
    void Promise.resolve(configureVault({ persist: webPersist, clearOnClose })).catch(() => undefined);
  }, [webPersist, clearOnClose, hydrated]);
  return <VaultContext.Provider value={value ?? vault}>{children}</VaultContext.Provider>;
}
