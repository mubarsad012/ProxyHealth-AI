// Page compression and rotation (ARCHITECTURE §3 `features/scan/compress.ts`, D-21). Images are
// resized to 1600 px on the longest edge and re-encoded as JPEG 0.8 (EXIF stripped) with the page
// rotation baked into the pixels, so the server always receives `rotation: 0` and the masks, the
// crops and the page the user saw share one coordinate frame. PDFs are read as-is.

import type { MaskRect } from '@/api/types';
import { normaliseMask, toDataUrl, toJpegBase64, type ImageInput } from '@/lib/image';
import { readPdfBase64 } from '@/lib/pdf';
import type { CapturedPage } from '@/store/session';

import { webFileFor } from './pick';

export const COMPRESS = { maxEdge: 1600, quality: 0.8 } as const;

function inputFor(page: CapturedPage): ImageInput {
  const file = webFileFor(page.id);
  // Once compressed, `uri` is a data: URL of our own JPEG; the original File is no longer needed.
  if (file && !page.uri.startsWith('data:')) return { file };
  return { uri: page.uri };
}

/** Resize to 1600 px max edge, JPEG 0.8, EXIF stripped, rotation baked in (→ `rotation: 0`). */
export async function compressPage(page: CapturedPage): Promise<CapturedPage> {
  if (page.mimeType === 'application/pdf') {
    if (page.base64) return page;
    const read = await readPdfBase64({ uri: page.uri, file: webFileFor(page.id) });
    return { ...page, base64: read.base64, byteLength: read.byteLength };
  }
  if (page.base64 && page.mimeType === 'image/jpeg' && page.rotation === 0 && page.uri.startsWith('data:')) {
    return page;
  }
  const out = await toJpegBase64(inputFor(page), { ...COMPRESS, rotation: page.rotation });
  return {
    ...page,
    uri: toDataUrl(out.base64, 'image/jpeg'),
    base64: out.base64,
    mimeType: 'image/jpeg',
    width: out.width,
    height: out.height,
    rotation: 0,
    masks: page.rotation ? rotateMasks(page.masks, page.rotation) : page.masks,
    byteLength: out.byteLength,
  };
}

/** Rotate normalised masks clockwise by `deg` (multiples of 90) — they follow the page. */
export function rotateMasks(masks: MaskRect[], deg: number): MaskRect[] {
  const turns = (((Math.round(deg / 90) % 4) + 4) % 4) as 0 | 1 | 2 | 3;
  return masks
    .map((m) => {
      let r = m;
      for (let i = 0; i < turns; i += 1) {
        // 90° clockwise: (x, y) → (1 - y, x)
        r = { x0: 1 - r.y1, x1: 1 - r.y0, y0: r.x0, y1: r.x1 };
      }
      return normaliseMask(r);
    })
    .filter((m): m is MaskRect => m !== null);
}

/** "Turn" on S5: bake a further 90° clockwise turn into the page right away (upright preview). */
export async function turnPage(page: CapturedPage): Promise<CapturedPage> {
  if (page.mimeType === 'application/pdf') return page;
  const next = ((page.rotation + 90) % 360) as CapturedPage['rotation'];
  return compressPage({ ...page, rotation: next });
}
