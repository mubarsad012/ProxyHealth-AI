// Count of enabled reminders in the next 7 days (PRODUCT_SPEC §5.7 `tabs.papers` badge). Reads the
// vault (the `Vault` interface has no `listUpcomingReminders`, so it filters client-side) and
// refreshes when `refreshKey` changes (e.g. the focused tab index).

import { useEffect, useState } from 'react';

import type { Reminder } from '@/storage/index';
import { useVault } from '@/storage/StorageProvider';

const WEEK_MS = 7 * 24 * 60 * 60 * 1000;

export function countUpcoming(reminders: Reminder[], now: number = Date.now()): number {
  return reminders.filter((r) => {
    if (!r.enabled) return false;
    const at = Date.parse(r.fireAt);
    return Number.isFinite(at) && at >= now && at - now <= WEEK_MS;
  }).length;
}

export function useUpcomingReminderCount(refreshKey?: unknown): number {
  const vault = useVault();
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    vault.reminders
      .list()
      .then((list) => {
        if (!cancelled) setCount(countUpcoming(list));
      })
      .catch(() => {
        if (!cancelled) setCount(0);
      });
    return () => {
      cancelled = true;
    };
  }, [vault, refreshKey]);
  return count;
}
