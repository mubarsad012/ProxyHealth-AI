// Memory-only session store (BUILD_PLAN §4.2 / §5.0; owner WP4 after M0).
// Holds the current scan pages, the unsaved analysis, the consent record, the server config, the
// data-use tier, the clerk-mode flag and the offline scan queue. Nothing here is persisted
// (D-22/D-23); "Delete everything" and app restarts clear it.

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

/** A scan captured offline, kept until connectivity returns (ARCHITECTURE §3.1 "Offline behaviors").
 *  The docs name the type without defining its fields (CL-014); WP4 may extend, never rename. */
export type QueuedScan = {
  id: string;
  pages: CapturedPage[];
  targetLanguage: string;
  memberId: string | null;
  queuedAt: string;
};

/** The tier the UI reasons about: the server's `DataUseTier` or `'unknown'` while `/v1/config`
 *  is unreachable. `'none'` (no keys configured) is rendered like `'unknown'` (PRODUCT_SPEC §5.3). */
export type UiTier = DataUseTier | 'unknown';

export interface SessionState {
  pages: CapturedPage[];
  demoSampleId: string | null;
  currentAnalysis: AnalysisResult | null;
  consent: ConsentRecord | null;
  serverConfig: ServerConfig | null;
  tier: UiTier;
  clerkMode: boolean;
  offlineQueue: QueuedScan[];
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
  enqueueOfflineScan(scan: QueuedScan): void;
  dequeueOfflineScan(id: string): void;
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
  offlineQueue: [],
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
  enqueueOfflineScan: (scan) => set((s) => ({ offlineQueue: [...s.offlineQueue, scan] })),
  dequeueOfflineScan: (id) =>
    set((s) => ({ offlineQueue: s.offlineQueue.filter((q) => q.id !== id) })),
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
