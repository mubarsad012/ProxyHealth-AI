// "Hide parts" mask geometry (D-19, PRODUCT_SPEC S5). Masks are normalised 0..1 rectangles over
// the upright page image. Native sends them as `pages[].masks`; web burns them on a canvas
// (`lib/image.burnMasksOnCanvas`) and sends `masks: []` + `masks_applied_client_side: true`.

import type { MaskRect } from '@/api/types';
import { normaliseMask } from '@/lib/image';

/** Rectangle from a drag between two points in view pixels (pure; exported for tests). */
export function maskFromDrag(
  start: { x: number; y: number },
  end: { x: number; y: number },
  view: { width: number; height: number },
): MaskRect | null {
  if (view.width <= 0 || view.height <= 0) return null;
  return normaliseMask({
    x0: start.x / view.width,
    y0: start.y / view.height,
    x1: end.x / view.width,
    y1: end.y / view.height,
  });
}

/** The non-drag alternative: a box of the given size centred on a tap (clamped inside the page). */
export function maskAround(center: { x: number; y: number }, half: { w: number; h: number } = { w: 0.2, h: 0.04 }): MaskRect {
  const cx = Math.min(1 - half.w, Math.max(half.w, center.x));
  const cy = Math.min(1 - half.h, Math.max(half.h, center.y));
  return { x0: cx - half.w, y0: cy - half.h, x1: cx + half.w, y1: cy + half.h };
}

/** Nudge a mask by a normalised delta, keeping it on the page. */
export function moveMask(m: MaskRect, dx: number, dy: number): MaskRect {
  const w = m.x1 - m.x0;
  const h = m.y1 - m.y0;
  const x0 = Math.min(1 - w, Math.max(0, m.x0 + dx));
  const y0 = Math.min(1 - h, Math.max(0, m.y0 + dy));
  return { x0, y0, x1: x0 + w, y1: y0 + h };
}

/** Grow/shrink a mask around its centre (handles on the tap-to-place box). */
export function resizeMask(m: MaskRect, dw: number, dh: number): MaskRect {
  const cx = (m.x0 + m.x1) / 2;
  const cy = (m.y0 + m.y1) / 2;
  const w = Math.min(1, Math.max(0.02, m.x1 - m.x0 + dw));
  const h = Math.min(1, Math.max(0.01, m.y1 - m.y0 + dh));
  return normaliseMask({ x0: cx - w / 2, y0: cy - h / 2, x1: cx + w / 2, y1: cy + h / 2 }) ?? m;
}

export function hasMasks(pages: { masks: MaskRect[]; mimeType: string }[]): boolean {
  return pages.some((p) => p.mimeType !== 'application/pdf' && p.masks.length > 0);
}
