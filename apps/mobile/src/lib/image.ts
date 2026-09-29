// Image helpers (BUILD_PLAN §4.2 seam, owner WP5; ARCHITECTURE §3 `lib/image.ts`; D-19, D-21).
// Native: expo-image-manipulator context API (SDK 57, verified against the installed 57.0.19
// types): `ImageManipulator.manipulate(uri).rotate(deg).resize({width|height}).renderAsync()` →
// `ImageRef.saveAsync({ compress, format: SaveFormat.JPEG, base64: true })`. Web: the picked
// `File` / blob: / data: URL is drawn on a `<canvas>` and re-encoded with `toDataURL('image/jpeg')`.
// Re-encoding drops EXIF on both paths. Nothing here writes to disk or sends anything anywhere.

import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { Platform } from 'react-native';

import type { MaskRect } from '@/api/types';

/** A native file URI or a DOM `File` (web picker / drag-drop). */
export type ImageInput = { uri: string } | { file: File };

export interface ToJpegOptions {
  /** Longest edge after resize (D-21 caps). */
  maxEdge: 1600;
  /** JPEG quality. */
  quality: 0.8;
  /** Degrees clockwise to apply before encoding. */
  rotation?: number;
}

export interface JpegResult {
  base64: string;
  width: number;
  height: number;
  byteLength: number;
}

/** Decoded byte length of a base64 string (no padding assumptions beyond RFC 4648). */
export function base64ByteLength(base64: string): number {
  const clean = stripDataUrl(base64).replace(/\s/g, '');
  if (!clean) return 0;
  const padding = clean.endsWith('==') ? 2 : clean.endsWith('=') ? 1 : 0;
  return Math.floor((clean.length * 3) / 4) - padding;
}

/** `data:image/jpeg;base64,AAAA` → `AAAA`; plain base64 is returned unchanged. */
export function stripDataUrl(value: string): string {
  const comma = value.startsWith('data:') ? value.indexOf(',') : -1;
  return comma >= 0 ? value.slice(comma + 1) : value;
}

export function toDataUrl(base64: string, mimeType: string = 'image/jpeg'): string {
  return base64.startsWith('data:') ? base64 : `data:${mimeType};base64,${base64}`;
}

/** Normalise a rotation to 0/90/180/270 clockwise. */
export function normaliseRotation(deg: number | undefined): 0 | 90 | 180 | 270 {
  const r = ((Math.round((deg ?? 0) / 90) * 90) % 360 + 360) % 360;
  return r as 0 | 90 | 180 | 270;
}

/** Target size that fits `maxEdge` without upscaling (pure; exported for tests). */
export function fitWithin(width: number, height: number, maxEdge: number): { width: number; height: number } {
  const longest = Math.max(width, height);
  if (!longest || longest <= maxEdge) return { width: Math.round(width), height: Math.round(height) };
  const scale = maxEdge / longest;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)) };
}

/** Clamp and order a mask rectangle into 0..1 with x0<x1, y0<y1; null when degenerate. */
export function normaliseMask(m: MaskRect): MaskRect | null {
  const c = (v: number) => Math.min(1, Math.max(0, v));
  const x0 = c(Math.min(m.x0, m.x1));
  const x1 = c(Math.max(m.x0, m.x1));
  const y0 = c(Math.min(m.y0, m.y1));
  const y1 = c(Math.max(m.y0, m.y1));
  if (x1 - x0 < 0.005 || y1 - y0 < 0.005) return null;
  return { x0, y0, x1, y1 };
}

// --- web (canvas) ------------------------------------------------------------------------------

function loadImageElement(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error('image_decode_failed'));
    img.src = src;
  });
}

async function webImageFrom(input: ImageInput): Promise<{ img: HTMLImageElement; revoke(): void }> {
  if ('file' in input) {
    const url = URL.createObjectURL(input.file);
    const img = await loadImageElement(url);
    return { img, revoke: () => URL.revokeObjectURL(url) };
  }
  // data: and blob: URLs load directly; anything else (http fixture pages) goes through a blob
  // so the canvas is never tainted by a cross-origin image.
  if (input.uri.startsWith('data:') || input.uri.startsWith('blob:')) {
    return { img: await loadImageElement(input.uri), revoke: () => undefined };
  }
  const res = await fetch(input.uri);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const img = await loadImageElement(url);
  return { img, revoke: () => URL.revokeObjectURL(url) };
}

function canvasToJpeg(canvas: HTMLCanvasElement, quality: number): JpegResult {
  const base64 = stripDataUrl(canvas.toDataURL('image/jpeg', quality));
  return { base64, width: canvas.width, height: canvas.height, byteLength: base64ByteLength(base64) };
}

async function toJpegWeb(input: ImageInput, opts: ToJpegOptions): Promise<JpegResult> {
  const { img, revoke } = await webImageFrom(input);
  try {
    const rotation = normaliseRotation(opts.rotation);
    const swap = rotation === 90 || rotation === 270;
    const srcW = img.naturalWidth || img.width;
    const srcH = img.naturalHeight || img.height;
    const target = fitWithin(swap ? srcH : srcW, swap ? srcW : srcH, opts.maxEdge);
    const canvas = document.createElement('canvas');
    canvas.width = target.width;
    canvas.height = target.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('canvas_unavailable');
    ctx.fillStyle = '#FFFFFF';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.translate(canvas.width / 2, canvas.height / 2);
    ctx.rotate((rotation * Math.PI) / 180);
    const drawW = swap ? target.height : target.width;
    const drawH = swap ? target.width : target.height;
    ctx.drawImage(img, -drawW / 2, -drawH / 2, drawW, drawH);
    return canvasToJpeg(canvas, opts.quality);
  } finally {
    revoke();
  }
}

// --- native (expo-image-manipulator) -----------------------------------------------------------

async function toJpegNative(input: ImageInput, opts: ToJpegOptions): Promise<JpegResult> {
  if (!('uri' in input)) throw new Error('native_requires_uri');
  const ctx = ImageManipulator.manipulate(input.uri);
  const rotation = normaliseRotation(opts.rotation);
  if (rotation) ctx.rotate(rotation);
  let ref = await ctx.renderAsync();
  if (Math.max(ref.width, ref.height) > opts.maxEdge) {
    ctx.resize(ref.width >= ref.height ? { width: opts.maxEdge } : { height: opts.maxEdge });
    ref = await ctx.renderAsync();
  }
  const out = await ref.saveAsync({ compress: opts.quality, format: SaveFormat.JPEG, base64: true });
  const base64 = out.base64 ?? '';
  if (!base64) throw new Error('encode_failed');
  return { base64, width: out.width, height: out.height, byteLength: base64ByteLength(base64) };
}

/** Resize to `maxEdge`, apply `rotation`, re-encode as JPEG (EXIF stripped) → base64. */
export function toJpegBase64(input: ImageInput, opts: ToJpegOptions): Promise<JpegResult> {
  if (Platform.OS === 'web') return toJpegWeb(input, opts);
  return toJpegNative(input, opts);
}

/** Burn "Hide parts" masks into the JPEG on a canvas — web only; throws on native (D-19).
 *  Input and output are plain base64 JPEG (a data: URL is accepted as input). */
export async function burnMasksOnCanvas(base64: string, masks: MaskRect[]): Promise<string> {
  if (Platform.OS !== 'web') throw new Error('burnMasksOnCanvas is web only (native sends masks[])');
  const img = await loadImageElement(toDataUrl(base64));
  const canvas = document.createElement('canvas');
  canvas.width = img.naturalWidth || img.width;
  canvas.height = img.naturalHeight || img.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('canvas_unavailable');
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#000000';
  for (const raw of masks) {
    const m = normaliseMask(raw);
    if (!m) continue;
    // Round outward so no partially covered pixel row survives.
    const x = Math.floor(m.x0 * canvas.width);
    const y = Math.floor(m.y0 * canvas.height);
    const w = Math.ceil(m.x1 * canvas.width) - x;
    const h = Math.ceil(m.y1 * canvas.height) - y;
    ctx.fillRect(x, y, w, h);
  }
  return stripDataUrl(canvas.toDataURL('image/jpeg', 0.8));
}
