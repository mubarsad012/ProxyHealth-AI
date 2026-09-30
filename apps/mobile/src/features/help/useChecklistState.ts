// "Before you go, bring" tick state per document. Saving is opt-in (D-22): ticks are written to
// the vault only when this paper is already saved there; otherwise they live in memory for the
// session and nothing is stored.

import { useCallback, useEffect, useState } from 'react';

import type { Vault } from '@/storage';
import { useVault } from '@/storage/StorageProvider';

const memory = new Map<string, Record<string, boolean>>();

async function isSaved(vault: Vault, documentId: string): Promise<boolean> {
  try {
    return (await vault.documents.get(documentId)) !== null;
  } catch {
    return false;
  }
}

export interface ChecklistStateApi {
  state: Record<string, boolean>;
  toggle(id: string, checked: boolean): void;
}

export function useChecklistState(documentId: string | null): ChecklistStateApi {
  const vault = useVault();
  const memKey = documentId ?? '__help_tab__';
  const [state, setState] = useState<Record<string, boolean>>(() => memory.get(memKey) ?? {});

  useEffect(() => {
    let cancelled = false;
    if (!documentId) return;
    (async () => {
      if (!(await isSaved(vault, documentId))) return;
      try {
        const stored = await vault.checklist.get(documentId);
        if (!cancelled) {
          const merged = { ...(memory.get(memKey) ?? {}), ...stored };
          memory.set(memKey, merged);
          setState(merged);
        }
      } catch {
        // storage unavailable: memory state stands
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [vault, documentId, memKey]);

  const toggle = useCallback(
    (id: string, checked: boolean) => {
      setState((prev) => {
        const next = { ...prev, [id]: checked };
        memory.set(memKey, next);
        return next;
      });
      if (documentId) {
        void (async () => {
          if (await isSaved(vault, documentId)) {
            try {
              await vault.checklist.set(documentId, id, checked);
            } catch {
              // keep the in-memory tick
            }
          }
        })();
      }
    },
    [vault, documentId, memKey],
  );

  return { state, toggle };
}
