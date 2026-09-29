// `POST /v1/troubleshoot` request building (API_CONTRACT §3.6). Exactly one image, never a PDF;
// `user_goal` ≤ 300 characters (limits.max_user_goal_chars). Pure.

import type { PageInput, PortalHint, TroubleshootMode, TroubleshootRequest } from '@/api/types';
import type { PlatformName } from '@/lib/platform';

export const MAX_GOAL_CHARS = 300;
export const SAMPLE_SCREENSHOT_ID = 'portal_file_too_large';

export const PORTAL_HINTS: readonly PortalHint[] = [
  'benefits_portal',
  'uscis_account',
  'eoir_portal',
  'school_portal',
  'hospital_portal',
  'insurer_portal',
  'irs_portal',
  'bank',
  'other',
];

export function parseMode(value: unknown): TroubleshootMode {
  return value === 'scam_check' ? 'scam_check' : 'portal';
}

export class NotAnImageError extends Error {
  constructor() {
    super('troubleshoot takes one image, not a PDF');
  }
}

export function clampGoal(goal: string | null | undefined, max: number = MAX_GOAL_CHARS): string | null {
  const trimmed = (goal ?? '').trim();
  return trimmed ? Array.from(trimmed).slice(0, max).join('') : null;
}

export function buildTroubleshootRequest(input: {
  screenshot: PageInput;
  mode: TroubleshootMode;
  goal?: string | null;
  portalHint?: PortalHint | null;
  language: string;
  platform: PlatformName;
  demoSampleId?: string | null;
  maxGoalChars?: number;
}): TroubleshootRequest {
  if (input.screenshot.mime_type === 'application/pdf') throw new NotAnImageError();
  return {
    screenshot: { ...input.screenshot, masks: input.screenshot.masks ?? [], rotation: input.screenshot.rotation ?? 0 },
    user_goal: clampGoal(input.goal, input.maxGoalChars),
    mode: input.mode,
    portal_hint: input.mode === 'portal' ? (input.portalHint ?? null) : null,
    target_language: input.language,
    demo_sample_id: input.demoSampleId ?? null,
    client_platform: input.platform,
  };
}
