// Consent record + decision over `kv` (D-02, D-22: there is no sqlite consent table).
// `ConsentRecord` is written only on "I understand, continue"; the separate decision marker
// remembers "Not now" and "Stop sending papers" so S0 can route without re-asking every launch.

import { Platform } from 'react-native';

import type { ConsentRecord } from '@/storage/index';
import { kv, KV_KEYS } from '@/storage/kv';

export type ConsentDecision = 'none' | 'accepted' | 'not_now' | 'withdrawn';

export interface ConsentDecisionRecord {
  decision: Exclude<ConsentDecision, 'none'>;
  at: string;
}

export type TierSeen = ConsentRecord['tier_seen'];

export function currentPlatform(): ConsentRecord['platform'] {
  if (Platform.OS === 'ios') return 'ios';
  if (Platform.OS === 'android') return 'android';
  return 'web';
}

export function buildConsentRecord(consentVersion: string, tierSeen: TierSeen): ConsentRecord {
  return {
    consent_version: consentVersion,
    accepted_at: new Date().toISOString(),
    tier_seen: tierSeen,
    platform: currentPlatform(),
  };
}

export const consentStore = {
  get(): Promise<ConsentRecord | null> {
    return kv.getJSON<ConsentRecord>(KV_KEYS.consent);
  },
  async set(record: ConsentRecord): Promise<void> {
    await kv.setJSON(KV_KEYS.consent, record);
    await kv.setJSON(KV_KEYS.consentDecision, {
      decision: 'accepted',
      at: record.accepted_at,
    } satisfies ConsentDecisionRecord);
  },
  async clear(): Promise<void> {
    await kv.remove(KV_KEYS.consent);
    await kv.remove(KV_KEYS.consentDecision);
  },
  async getDecision(): Promise<ConsentDecision> {
    const d = await kv.getJSON<ConsentDecisionRecord>(KV_KEYS.consentDecision);
    return d?.decision ?? 'none';
  },
  /** "Not now": no record, but the decision is remembered so S0 goes to the tabs. */
  async setNotNow(): Promise<void> {
    await kv.remove(KV_KEYS.consent);
    await kv.setJSON(KV_KEYS.consentDecision, {
      decision: 'not_now',
      at: new Date().toISOString(),
    } satisfies ConsentDecisionRecord);
  },
  /** "Stop sending papers": record removed, uploads disabled until S2 is accepted again. */
  async withdraw(): Promise<void> {
    await kv.remove(KV_KEYS.consent);
    await kv.setJSON(KV_KEYS.consentDecision, {
      decision: 'withdrawn',
      at: new Date().toISOString(),
    } satisfies ConsentDecisionRecord);
  },
};

/** D-02: re-show S2 when the server's consent version or the tier differs from what was seen. */
export function consentIsCurrent(
  record: ConsentRecord | null,
  serverConsentVersion: string | null,
  tierNow: TierSeen | null,
): boolean {
  if (!record) return false;
  if (serverConsentVersion && record.consent_version !== serverConsentVersion) return false;
  if (tierNow && tierNow !== 'unknown' && record.tier_seen !== tierNow) return false;
  return true;
}
