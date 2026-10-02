// S16 "Hide parts" on the screenshot preview (PRODUCT_SPEC S16: "masks allowed; same burn/mask
// rules as S5", D-19). The boxes are drawn with S5's `MaskEditor` on a `CapturedPage` view of the
// screenshot, then sent exactly like S5 sends a page (`features/analysis/buildRequest.ts`):
//   web    → burned into the JPEG on a canvas (`lib/image.burnMasksOnCanvas`), `masks: []`;
//   native → the normalised `masks[]` travel with the bytes and the server burns them
//            (`analysis/troubleshoot_pipeline.py` → `redaction.redact_image`) before inference.
// "Save as proof" may store only pixels that have the boxes burned in (nothing unmasked is ever
// stored): the web burned copy, or the original when there are no boxes. Native with boxes keeps
// no proof image, so the button is not offered.

import type { MaskRect, PageInput } from '@/api/types';
import { burnMasksOnCanvas, normaliseMask, toDataUrl } from '@/lib/image';
import type { CapturedPage } from '@/store/session';

import type { Screenshot } from './pick';

export const SCREENSHOT_PAGE_ID = 'troubleshoot-screenshot';

/** Normalised boxes (0–1, x0 < x1, y0 < y1); tiny or empty boxes are dropped. */
export function cleanMasks(masks: readonly MaskRect[]): MaskRect[] {
  return masks.map(normaliseMask).filter((m): m is MaskRect => m !== null);
}

/** The screenshot as the `CapturedPage` that `MaskEditor` edits (one page, never rotated). */
export function screenshotPage(shot: Screenshot, masks: MaskRect[]): CapturedPage {
  return {
    id: SCREENSHOT_PAGE_ID,
    uri: shot.uri,
    base64: shot.base64,
    mimeType: shot.mimeType,
    width: shot.width,
    height: shot.height,
    rotation: 0,
    masks,
    source: 'library',
  };
}

export interface PreparedScreenshot {
  /** What `POST /v1/troubleshoot` receives as `screenshot`. */
  input: PageInput;
  /** Pixels that may be stored as proof (boxes burned in), or null when there are none. */
  proof: Screenshot | null;
}

export interface PrepareDeps {
  burn(base64: string, masks: MaskRect[]): Promise<string>;
}

const defaultDeps: PrepareDeps = { burn: burnMasksOnCanvas };

/**
 * The request body part for a screenshot with its boxes. Never sends unmasked pixels on web: if
 * the canvas burn fails, this rejects and nothing is sent.
 */
export async function prepareScreenshot(
  shot: Screenshot,
  rawMasks: readonly MaskRect[],
  platform: 'web' | 'ios' | 'android',
  deps: PrepareDeps = defaultDeps,
): Promise<PreparedScreenshot> {
  const masks = cleanMasks(rawMasks);
  if (masks.length === 0) {
    return { input: { mime_type: shot.mimeType, data_base64: shot.base64, masks: [], rotation: 0 }, proof: shot };
  }
  if (platform === 'web') {
    const burned = await deps.burn(shot.base64, masks);
    return {
      input: { mime_type: 'image/jpeg', data_base64: burned, masks: [], rotation: 0 },
      proof: { ...shot, base64: burned, mimeType: 'image/jpeg', uri: toDataUrl(burned) },
    };
  }
  return { input: { mime_type: shot.mimeType, data_base64: shot.base64, masks, rotation: 0 }, proof: null };
}
