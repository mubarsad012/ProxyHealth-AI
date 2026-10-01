// StorageProvider (ARCHITECTURE §3 `_layout.tsx` providers): exposes the platform vault and keeps the
// web persistence mode (session ⇄ IndexedDB, clear-on-close) in step with Settings (D-23). The
// native database opens lazily on first use, so nothing here blocks the first render.

import { createContext, type ReactNode, useContext, useEffect, useState } from 'react';
import { Platform } from 'react-native';

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
  // Web: switching to / from IndexedDB loads or drops records after the first lists were read, so
  // hand out a fresh reference once it settles — every `[vault, …]` reader then re-reads (papers
  // kept with "Keep on this device" show up after a reload instead of an empty list).
  const [current, setCurrent] = useState<Vault>(vault);
  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;
    void Promise.resolve(configureVault({ persist: webPersist, clearOnClose }))
      .then(() => {
        if (!cancelled && Platform.OS === 'web') setCurrent({ ...vault });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [webPersist, clearOnClose, hydrated]);
  return <VaultContext.Provider value={value ?? current}>{children}</VaultContext.Provider>;
}
