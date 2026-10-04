// Memory-only session store (BUILD_PLAN §4.2 / §5.0; owner WP4 after M0).
// Holds the current scan pages, the unsaved analysis, the consent record, the server config, the
// data-use tier and the clerk-mode flag. Nothing here is persisted (D-22/D-23); "Delete
// everything" and app restarts clear it. There is no offline scan queue: an offline scan is saved
// to read later or waits on S5 for the connection (CL-064, CL-085(c) — the never-drained
// `offlineQueue` / `enqueueOfflineScan` / `QueuedScan` were removed in Phase 3).

import { create } from 'zustand';

import type { AnalysisResult, DataUseTier, MaskRect, ServerConfig } from '@/api/types';
import type { ConsentRecord } from '@/storage';

export type { MaskRect, ServerConfig } from '@/api/types';
export type { ConsentRecord } from '@/storage';

export type CapturedPageMime =
  | 'image/jpeg'
  | 'image/png'
  | 'image/webp'
  | 'image/heic'
  | 'image/heif'
  | 'application/pdf';

export type CapturedPage = {
  id: string;
  uri: string;
  base64?: string;
  mimeType: CapturedPageMime;
  width?: number;
  height?: number;
  rotation: 0 | 90 | 180 | 270;
  masks: MaskRect[];
  source: 'camera' | 'library' | 'pdf' | 'sample';
  fileName?: string;
  byteLength?: number;
};

/** The tier the UI reasons about: the server's `DataUseTier` or `'unknown'` while `/v1/config`
 *  is unreachable. `'none'` (no keys configured) is rendered like `'unknown'` (PRODUCT_SPEC §5.3).
 *  `'local'` / `'attested'` (Phase 3, `AI_PROVIDER=openai_compat`) allow real papers like `'paid'`
 *  when `features.real_documents_allowed` says so (free-ai-providers §5.2). */
export type UiTier = DataUseTier | 'unknown';

export interface SessionState {
  pages: CapturedPage[];
  demoSampleId: string | null;
  currentAnalysis: AnalysisResult | null;
  consent: ConsentRecord | null;
  serverConfig: ServerConfig | null;
  tier: UiTier;
  clerkMode: boolean;
  /** ISO time until which the helper is out of quota (now + `retry_after_seconds` after a
   *  `quota_exhausted` error; set by `api/client.ts`, read by S3 `home.busy_until` — CL-039). */
  quotaCoolingUntil: string | null;
}

export interface SessionActions {
  setPages(pages: CapturedPage[]): void;
  addPage(page: CapturedPage): void;
  removePage(id: string): void;
  updatePage(id: string, patch: Partial<CapturedPage>): void;
  clearPages(): void;
  setDemoSampleId(id: string | null): void;
  setCurrentAnalysis(analysis: AnalysisResult | null): void;
  setConsent(consent: ConsentRecord | null): void;
  setServerConfig(config: ServerConfig | null): void;
  setTier(tier: UiTier): void;
  setClerkMode(on: boolean): void;
  setQuotaCoolingUntil(iso: string | null): void;
  reset(): void;
}

export type SessionStore = SessionState & SessionActions;

export const initialSessionState: SessionState = {
  pages: [],
  demoSampleId: null,
  currentAnalysis: null,
  consent: null,
  serverConfig: null,
  tier: 'unknown',
  clerkMode: false,
  quotaCoolingUntil: null,
};

export const useSession = create<SessionStore>()((set) => ({
  ...initialSessionState,
  setPages: (pages) => set({ pages }),
  addPage: (page) => set((s) => ({ pages: [...s.pages, page] })),
  removePage: (id) => set((s) => ({ pages: s.pages.filter((p) => p.id !== id) })),
  updatePage: (id, patch) =>
    set((s) => ({ pages: s.pages.map((p) => (p.id === id ? { ...p, ...patch } : p)) })),
  clearPages: () => set({ pages: [], demoSampleId: null }),
  setDemoSampleId: (demoSampleId) => set({ demoSampleId }),
  setCurrentAnalysis: (currentAnalysis) => set({ currentAnalysis }),
  setConsent: (consent) => set({ consent }),
  setServerConfig: (serverConfig) =>
    set({ serverConfig, tier: serverConfig ? serverConfig.data_use_tier : 'unknown' }),
  setTier: (tier) => set({ tier }),
  setClerkMode: (clerkMode) => set({ clerkMode }),
  setQuotaCoolingUntil: (quotaCoolingUntil) => set({ quotaCoolingUntil }),
  reset: () => set({ ...initialSessionState }),
}));

/** The consent version the API client sends as `X-Consent-Version` (null → header omitted). */
export function currentConsentVersion(): string | null {
  return useSession.getState().consent?.consent_version ?? null;
}

/** True when real (non-sample) uploads are allowed: consent given and the tier permits them. */
export function realUploadsAllowed(state: SessionState = useSession.getState()): boolean {
  if (!state.consent) return false;
  if (state.tier === 'unknown' || state.tier === 'none') return false;
  if (state.tier === 'unpaid' || state.tier === 'mixed') return false;
  return state.serverConfig?.features.real_documents_allowed !== false;
}
