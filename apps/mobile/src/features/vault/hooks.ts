// Vault read hooks (BUILD_PLAN §4.2 seam: `useDocument`, `useNextDate`) plus the list hooks S12,
// S13, S14 and Home use. Each re-reads when `useVaultVersion` changes (any WP6 write or wipe).

import { useEffect, useState } from 'react';

import type { DocumentRow, Member, Reminder, StoredDocument } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';

import { sortRows } from './documents';
import { withMe } from './members';
import { type NextDate, pickNextDate } from './nextDate';
import { useVaultVersion } from './store';

export { NEXT_DATE_WINDOW_DAYS, type NextDate, pickNextDate } from './nextDate';

function useLoad<T>(initial: T, load: () => Promise<T>, deps: unknown[]): { value: T; loading: boolean } {
  const [state, setState] = useState<{ value: T; loading: boolean }>({ value: initial, loading: true });
  useEffect(() => {
    let cancelled = false;
    // Stale-while-revalidate: the previous value stays on screen until the new read lands.
    load()
      .then((value) => {
        if (!cancelled) setState({ value, loading: false });
      })
      .catch(() => {
        if (!cancelled) setState({ value: initial, loading: false });
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

/** One stored document (null while loading or when missing). `doc.analysis` may be null for
 *  "Save to read later" rows (CL-024(c)). */
export function useDocument(id: string): { doc: StoredDocument | null; loading: boolean } {
  const vault = useVault();
  const version = useVaultVersion((s) => s.version);
  const { value, loading } = useLoad<StoredDocument | null>(
    null,
    () => (id ? vault.documents.get(id) : Promise.resolve(null)),
    [vault, id, version],
  );
  return { doc: value, loading };
}

export function useMembers(): { members: Member[]; loading: boolean } {
  const vault = useVault();
  const version = useVaultVersion((s) => s.version);
  const { value, loading } = useLoad<Member[]>(withMe([]), async () => withMe(await vault.members.list()), [
    vault,
    version,
  ]);
  return { members: value, loading };
}

/** Rows (optionally for one member or matching a search), in S12 order. */
export function useDocuments(opts: { memberId?: string; query?: string } = {}): {
  rows: DocumentRow[];
  loading: boolean;
} {
  const vault = useVault();
  const version = useVaultVersion((s) => s.version);
  const { memberId, query } = opts;
  const { value, loading } = useLoad<DocumentRow[]>(
    [],
    async () => {
      const q = (query ?? '').trim();
      const rows = q ? await vault.documents.search(q) : await vault.documents.list(memberId);
      const filtered = memberId ? rows.filter((r) => r.memberId === memberId) : rows;
      return sortRows(filtered, new Date());
    },
    [vault, version, memberId, query],
  );
  return { rows: value, loading };
}

export function useAllReminders(): { reminders: Reminder[]; loading: boolean } {
  const vault = useVault();
  const version = useVaultVersion((s) => s.version);
  const { value, loading } = useLoad<Reminder[]>([], () => vault.reminders.list(), [vault, version]);
  return { reminders: value, loading };
}

/** The next upcoming date across stored papers and own reminders (Home "next date" card). */
export function useNextDate(): { documentId: string; title: string; dateIso: string } | null {
  const vault = useVault();
  const version = useVaultVersion((s) => s.version);
  const { value } = useLoad<NextDate | null>(
    null,
    async () => {
      const [rows, reminders] = await Promise.all([vault.documents.list(), vault.reminders.list()]);
      return pickNextDate(rows, reminders, new Date());
    },
    [vault, version],
  );
  return value;
}
