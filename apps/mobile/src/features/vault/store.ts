// Tiny change signal for vault-backed lists (papers, member detail, reminders, Home next date).
// Anything that writes to the vault through WP6 code calls `bumpVault()`; readers re-query when
// `useVaultVersion` changes. Holds no document data. "Delete everything" bumps it too.

import { create } from 'zustand';

import { registerWipeHook } from '@/storage/wipe';

interface VaultVersionState {
  version: number;
  bump(): void;
}

export const useVaultVersion = create<VaultVersionState>()((set) => ({
  version: 0,
  bump: () => set((s) => ({ version: s.version + 1 })),
}));

export function bumpVault(): void {
  useVaultVersion.getState().bump();
}

// Lists re-read (and find nothing) once "Delete everything" has run.
registerWipeHook(() => {
  setTimeout(bumpVault, 0);
});
