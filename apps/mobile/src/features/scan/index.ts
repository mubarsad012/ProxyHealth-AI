// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP5. Keep every export name and signature.
// On web the picker call must be the first statement inside the button's onPress (gesture-safe),
// which is why both pickers accept the press event.

import type { CapturedPage } from '@/store/session';

export interface PickImageApi {
  pickFromLibrary(e?: unknown): Promise<CapturedPage[]>;
  pickPdf(e?: unknown): Promise<CapturedPage | null>;
}

/** Day-0 stub: both pickers reject with 'not implemented'. */
export function usePickImage(): PickImageApi {
  return {
    pickFromLibrary: () => Promise.reject(new Error('not implemented')),
    pickPdf: () => Promise.reject(new Error('not implemented')),
  };
}

/** Resize to 1600 px max edge, JPEG 0.8, EXIF stripped. Day-0 stub rejects. */
export function compressPage(_page: CapturedPage): Promise<CapturedPage> {
  return Promise.reject(new Error('not implemented'));
}
