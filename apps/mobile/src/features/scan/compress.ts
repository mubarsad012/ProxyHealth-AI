// Page compression and rotation (ARCHITECTURE §3 `features/scan/compress.ts`, D-21). Images are
// resized to 1600 px on the longest edge and re-encoded as JPEG 0.8 (EXIF stripped) with the page
// rotation baked into the pixels, so the server always receives `rotation: 0` and the masks, the
// crops and the page the user saw share one coordinate frame. PDFs are read as-is.
// Native temp files: once a page's compressed base64 exists, a camera / picker / document-picker
// original under `Paths.cache` is deleted (`lib/image.deleteCaptureTemp`) and the session's copy of
// that page is swapped to the compressed data first, so nothing on screen still points at the
// deleted file. Two callers compressing the same page at once (S5's on-arrival pass and "Read this
// paper" or "Turn") share one job, so the original is never read after it was deleted. A caller
// still holding a snapshot taken before the swap (useAnalyze hands over `session.pages` at the tap)
// gets the finished JPEG of that very original instead of re-reading the deleted file; it is kept
// only while the page is in the session. A shared or finished job always returns the caller's own
// hidden parts (boxes drawn while the page was being prepared are never dropped).

import type { MaskRect } from '@/api/types';
import { deleteCaptureTemp, isCaptureTemp, normaliseMask, toDataUrl, toJpegBase64, type ImageInput } from '@/lib/image';
import { readPdfBase64 } from '@/lib/pdf';
import { type CapturedPage, useSession } from '@/store/session';

import { webFileFor } from './pick';

export const COMPRESS = { maxEdge: 1600, quality: 0.8 } as const;

function inputFor(page: CapturedPage): ImageInput {
  const file = webFileFor(page.id);
  // Once compressed, `uri` is a data: URL of our own JPEG; the original File is no longer needed.
  if (file && !page.uri.startsWith('data:')) return { file };
  return { uri: page.uri };
}

/** True when `compressPage` has nothing left to do for this page. */
export function isCompressed(page: CapturedPage): boolean {
  if (page.mimeType === 'application/pdf') return Boolean(page.base64);
  return Boolean(page.base64) && page.mimeType === 'image/jpeg' && page.rotation === 0 && page.uri.startsWith('data:');
}

interface Job {
  /** The page the job compresses (its masks are the ones in `out`). */
  source: CapturedPage;
  out: Promise<CapturedPage>;
}

const inflight = new Map<string, Job>();

/** Finished compressions of deleted temp originals, by `jobKey` (pruned when the page leaves the
 *  session, so nothing outlives the scan). */
const released = new Map<string, { source: CapturedPage; out: CapturedPage }>();

useSession.subscribe((state) => {
  if (!released.size) return;
  const ids = new Set(state.pages.map((p) => p.id));
  for (const [key, done] of released) if (!ids.has(done.source.id)) released.delete(key);
});

function jobKey(page: CapturedPage): string {
  return `${page.id}|${page.rotation}|${page.uri.startsWith('data:') ? 'data' : page.uri}`;
}

/** `out` (compressed from `source`) with the caller's own masks, turned like the pixels. */
function forCaller(page: CapturedPage, source: CapturedPage, out: CapturedPage): CapturedPage {
  if (page.masks === source.masks) return out;
  return { ...out, masks: page.rotation ? rotateMasks(page.masks, page.rotation) : page.masks };
}

/**
 * The page's temp original is no longer needed: point the session's page (if it still shows that
 * very file, unchanged rotation) at the compressed data, then delete the file. Masks drawn in the
 * meantime are kept. Native only (web pages live in memory).
 */
function releaseTempSource(original: CapturedPage, compressed: CapturedPage): void {
  if (!isCaptureTemp(original.uri)) return;
  const session = useSession.getState();
  const current = session.pages.find((p) => p.id === original.id);
  if (current) released.set(jobKey(original), { source: original, out: compressed });
  if (current && current.uri === original.uri && current.rotation === original.rotation) {
    session.updatePage(original.id, { ...compressed, masks: original.rotation ? compressed.masks : current.masks });
  }
  deleteCaptureTemp(original.uri);
}

/** Resize to 1600 px max edge, JPEG 0.8, EXIF stripped, rotation baked in (→ `rotation: 0`).
 *  PDFs are read to base64 as they are. A native capture temp original is deleted afterwards. */
export function compressPage(page: CapturedPage): Promise<CapturedPage> {
  if (isCompressed(page)) return Promise.resolve(page);
  const key = jobKey(page);
  const done = released.get(key);
  if (done) return Promise.resolve(forCaller(page, done.source, done.out));
  const running = inflight.get(key);
  if (running) return running.out.then((out) => forCaller(page, running.source, out));
  const out = compressNow(page)
    .then((compressed) => {
      releaseTempSource(page, compressed);
      return compressed;
    })
    .finally(() => inflight.delete(key));
  inflight.set(key, { source: page, out });
  return out;
}

/** A compression of this page (any rotation) is running. */
export function isCompressing(pageId: string): boolean {
  for (const key of inflight.keys()) if (key.startsWith(`${pageId}|`)) return true;
  return false;
}

/** S5 "Remove" / "Take again": the page is gone, so its temp original goes too (unless a running
 *  compression still reads it — that job deletes it when it finishes). */
export function discardPageFiles(page: CapturedPage): void {
  if (isCompressing(page.id)) return;
  deleteCaptureTemp(page.uri);
}

async function compressNow(page: CapturedPage): Promise<CapturedPage> {
  if (page.mimeType === 'application/pdf') {
    const read = await readPdfBase64({ uri: page.uri, file: webFileFor(page.id) });
    return { ...page, base64: read.base64, byteLength: read.byteLength };
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

/** "Turn" on S5: bake a further 90° clockwise turn into the page right away (upright preview).
 *  The page is first compressed as it is (sharing a running on-arrival job), then turned from
 *  that JPEG, so a native temp original is read once and then deleted. */
export async function turnPage(page: CapturedPage): Promise<CapturedPage> {
  if (page.mimeType === 'application/pdf') return page;
  const base = isCaptureTemp(page.uri) ? await compressPage(page) : page;
  const next = ((base.rotation + 90) % 360) as CapturedPage['rotation'];
  return compressPage({ ...base, rotation: next });
}
