// "Delete everything" (PRODUCT_SPEC S17 item 8, COMPLIANCE_PRIVACY §9.5 order):
//   1. cancel every scheduled notification, 2–3. vault files + database (web: memory + IndexedDB),
//   4. SecureStore items, 5. every `kv` key (settings, consent, pack cache, config cache, install id),
//   6. install id forgotten (a new one is generated lazily at the next consent — CL-010),
//   7. in-memory stores reset; the caller then routes to S1 (`/onboarding/language`).
// Extra steps registered by feature packages (e.g. WP6 reminder bookkeeping) run after step 1;
// hooks registered with phase 'memory' (in-memory caches such as the consent decision) run in step 7,
// after `kv` is empty, so nothing can re-read the old values.

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
export type WipeHookPhase = 'hooks' | 'memory';
const hooks: Record<WipeHookPhase, Set<WipeHook>> = { hooks: new Set(), memory: new Set() };

/**
 * Feature packages register cleanup that must run during "Delete everything". The default phase
 * runs right after notifications are cancelled; `'memory'` runs in the final in-memory reset step.
 */
export function registerWipeHook(hook: WipeHook, phase: WipeHookPhase = 'hooks'): () => void {
  hooks[phase].add(hook);
  return () => {
    hooks[phase].delete(hook);
  };
}

async function runHooks(phase: WipeHookPhase): Promise<void> {
  for (const h of hooks[phase]) {
    try {
      await h();
    } catch {
      // One failing hook must not stop the others.
    }
  }
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
  await step('hooks', done, () => runHooks('hooks'));
  await step('vault', done, () => vault.wipeAll());
  await step('secure', done, () => clearSecure());
  await step('settings', done, () => useSettings.getState().resetSettings());
  await step('kv', done, () => kv.clearAll());
  await step('install_id', done, () => clearInstallId());
  await step('memory', done, async () => {
    try {
      useSession.getState().reset();
      useI18n.getState().setPack(EN_PACK);
      resetServerConfigSession();
    } finally {
      await runHooks('memory');
    }
  });
  return done;
}
