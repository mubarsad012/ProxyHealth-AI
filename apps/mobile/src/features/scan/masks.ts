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

/** Step of the non-drag move / size buttons (normalised page units). */
export const MASK_STEP = { move: 0.02, grow: { w: 0.04, h: 0.01 } } as const;

/** Drag the bottom-end corner handle: the top-left corner stays, the box keeps a minimum size. */
export function resizeFromCorner(m: MaskRect, dx: number, dy: number): MaskRect {
  const x1 = Math.min(1, Math.max(m.x0 + 0.02, m.x1 + dx));
  const y1 = Math.min(1, Math.max(m.y0 + 0.01, m.y1 + dy));
  return { x0: m.x0, y0: m.y0, x1, y1 };
}

export type MaskHit = { kind: 'handle' | 'body'; index: number } | null;

/**
 * What a touch at `point` (view pixels) lands on: the selected box's corner handle (within
 * `handlePx` of its bottom-right corner), else the top-most box containing it, else nothing
 * (the touch then draws or places a new box). Pure; exported for tests.
 */
export function hitTestMask(
  masks: readonly MaskRect[],
  point: { x: number; y: number },
  view: { width: number; height: number },
  selected: number | null,
  handlePx = 22,
): MaskHit {
  if (view.width <= 0 || view.height <= 0) return null;
  const sel = selected !== null ? masks[selected] : undefined;
  if (sel && selected !== null) {
    const cx = sel.x1 * view.width;
    const cy = sel.y1 * view.height;
    if (Math.abs(point.x - cx) <= handlePx && Math.abs(point.y - cy) <= handlePx) return { kind: 'handle', index: selected };
  }
  const px = point.x / view.width;
  const py = point.y / view.height;
  for (let i = masks.length - 1; i >= 0; i -= 1) {
    const m = masks[i];
    if (px >= m.x0 && px <= m.x1 && py >= m.y0 && py <= m.y1) return { kind: 'body', index: i };
  }
  return null;
}

/** Replace the box at `index` (no-op for a bad index). */
export function replaceMask(masks: readonly MaskRect[], index: number, next: MaskRect): MaskRect[] {
  if (index < 0 || index >= masks.length) return [...masks];
  return masks.map((m, i) => (i === index ? next : m));
}
