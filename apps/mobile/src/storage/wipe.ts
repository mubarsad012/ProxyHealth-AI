// "Delete everything" (PRODUCT_SPEC S17 item 8, COMPLIANCE_PRIVACY §9.5 order):
//   1. cancel every scheduled notification, 2–3. vault files + database (web: memory + IndexedDB),
//   4. SecureStore items, 5. every `kv` key (settings, consent, pack cache, config cache, install id),
//   6. install id forgotten (a new one is generated lazily at the next consent — CL-010),
//   7. in-memory stores reset; the caller then routes to S1 (`/onboarding/language`).
// Extra steps registered by feature packages (e.g. WP6 reminder bookkeeping) run after step 1.

import { clearInstallId } from '@/lib/ids';
import { resetServerConfigSession } from '@/api/config';
import { EN_PACK, useI18n } from '@/i18n/store';
import { kv } from '@/storage/kv';
import { clearSecure } from '@/storage/secure';
import { cancelAllNotifications, vault } from '@/storage/vault';
import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

export type WipeStep =
  | 'notifications'
  | 'hooks'
  | 'vault'
  | 'secure'
  | 'settings'
  | 'kv'
  | 'install_id'
  | 'memory';

type WipeHook = () => Promise<void> | void;
const hooks = new Set<WipeHook>();

/** Feature packages register cleanup that must run during "Delete everything". */
export function registerWipeHook(hook: WipeHook): () => void {
  hooks.add(hook);
  return () => hooks.delete(hook);
}

async function step(name: WipeStep, done: WipeStep[], fn: () => Promise<void> | void): Promise<void> {
  try {
    await fn();
  } catch {
    // Keep going: a failed step must never leave later data behind.
  }
  done.push(name);
}

/** Runs every step even if one fails; resolves with the order that ran (tests assert it). */
export async function wipeEverything(): Promise<WipeStep[]> {
  const done: WipeStep[] = [];
  await step('notifications', done, () => cancelAllNotifications());
  await step('hooks', done, async () => {
    for (const h of hooks) await h();
  });
  await step('vault', done, () => vault.wipeAll());
  await step('secure', done, () => clearSecure());
  await step('settings', done, () => useSettings.getState().resetSettings());
  await step('kv', done, () => kv.clearAll());
  await step('install_id', done, () => clearInstallId());
  await step('memory', done, () => {
    useSession.getState().reset();
    useI18n.getState().setPack(EN_PACK);
    resetServerConfigSession();
  });
  return done;
}
