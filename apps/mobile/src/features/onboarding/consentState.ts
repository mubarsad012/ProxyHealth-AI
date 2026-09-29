// Consent state for the running app (D-02). The record lives in `kv` (storage/consent.ts); this
// module loads it once into `session.consent` (the API client reads `X-Consent-Version` from
// there) and keeps the decision ("accepted" / "not_now" / "withdrawn" / "none") in a tiny store so
// S0, S2, S3 and S17 agree. The install id is created lazily at consent (CL-010).

import { create } from 'zustand';

import { getInstallId } from '@/lib/ids';
import type { ConsentRecord } from '@/storage/index';
import { buildConsentRecord, type ConsentDecision, consentStore, type TierSeen } from '@/storage/consent';
import { useSession } from '@/store/session';

interface ConsentDecisionState {
  decision: ConsentDecision;
  loaded: boolean;
  set(decision: ConsentDecision): void;
  setLoaded(loaded: boolean): void;
}

export const useConsentDecision = create<ConsentDecisionState>()((set) => ({
  decision: 'none',
  loaded: false,
  set: (decision) => set({ decision }),
  setLoaded: (loaded) => set({ loaded }),
}));

let loading: Promise<void> | null = null;

/** Read the stored record + decision once per session into memory. */
export function loadConsent(): Promise<void> {
  if (!loading) {
    loading = (async () => {
      const [record, decision] = await Promise.all([consentStore.get(), consentStore.getDecision()]);
      useSession.getState().setConsent(decision === 'accepted' ? record : null);
      useConsentDecision.getState().set(decision === 'accepted' && !record ? 'none' : decision);
      useConsentDecision.getState().setLoaded(true);
    })().catch(() => {
      useConsentDecision.getState().setLoaded(true);
    });
  }
  return loading;
}

/** Tests / "Delete everything": forget what was loaded. */
export function resetConsentState(): void {
  loading = null;
  useConsentDecision.setState({ decision: 'none', loaded: false });
}

/** "I understand, continue": store `{consent_version, accepted_at, tier_seen, platform}`. */
export async function acceptConsent(consentVersion: string, tierSeen: TierSeen): Promise<ConsentRecord> {
  const record = buildConsentRecord(consentVersion, tierSeen);
  await consentStore.set(record);
  useSession.getState().setConsent(record);
  useConsentDecision.getState().set('accepted');
  await getInstallId();
  return record;
}

/** "Not now" (also Android back / swipe-dismiss): no record; scan tiles disabled on Home. */
export async function declineConsent(): Promise<void> {
  await consentStore.setNotNow();
  useSession.getState().setConsent(null);
  useConsentDecision.getState().set('not_now');
}

/** Settings → "Stop sending papers". */
export async function withdrawConsent(): Promise<void> {
  await consentStore.withdraw();
  useSession.getState().setConsent(null);
  useConsentDecision.getState().set('withdrawn');
}

/** The previously accepted record (for the re-consent highlight), read straight from `kv`. */
export function previousRecord(): Promise<ConsentRecord | null> {
  return consentStore.get();
}
