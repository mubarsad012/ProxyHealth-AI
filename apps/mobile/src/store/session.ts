// Memory-only session store (BUILD_PLAN §4.2 / §5.0; owner WP4 after M0).
// Day-0 content: the `CapturedPage`, `QueuedScan` types, re-exports of the contract types
// `MaskRect` / `ServerConfig` and the storage type `ConsentRecord`, and a zustand store with the
// listed fields and no-op setters. Nothing here is persisted (D-22/D-23).

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

export interface SessionState {
  pages: CapturedPage[];
  demoSampleId: string | null;
  currentAnalysis: AnalysisResult | null;
  consent: ConsentRecord | null;
  serverConfig: ServerConfig | null;
  tier: DataUseTier | 'unknown';
  clerkMode: boolean;
  offlineQueue: QueuedScan[];
}

export interface SessionActions {
  setPages(pages: CapturedPage[]): void;
  addPage(page: CapturedPage): void;
  removePage(id: string): void;
  clearPages(): void;
  setDemoSampleId(id: string | null): void;
  setCurrentAnalysis(analysis: AnalysisResult | null): void;
  setConsent(consent: ConsentRecord | null): void;
  setServerConfig(config: ServerConfig | null): void;
  setTier(tier: DataUseTier | 'unknown'): void;
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

const noop = (): void => {};

/** Day-0 store: fields present, setters are no-ops until WP4 fills them. */
export const useSession = create<SessionStore>()(() => ({
  ...initialSessionState,
  setPages: noop,
  addPage: noop,
  removePage: noop,
  clearPages: noop,
  setDemoSampleId: noop,
  setCurrentAnalysis: noop,
  setConsent: noop,
  setServerConfig: noop,
  setTier: noop,
  setClerkMode: noop,
  enqueueOfflineScan: noop,
  dequeueOfflineScan: noop,
  reset: noop,
}));
