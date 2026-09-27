// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP5. Keep every export name and signature.
// Native: expo-image-manipulator resize/rotate/JPEG + File(uri).base64(); web: File → canvas → JPEG.
// EXIF is stripped by re-encoding; nothing is written to disk on the server.

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

/** Resize + re-encode to JPEG base64. Day-0 stub rejects with 'not implemented'. */
export function toJpegBase64(_input: ImageInput, _opts: ToJpegOptions): Promise<JpegResult> {
  return Promise.reject(new Error('not implemented'));
}

/** Burn "Hide parts" masks into the JPEG on a canvas — web only; throws on native (D-19).
 *  Day-0 stub rejects with 'not implemented'. */
export function burnMasksOnCanvas(_base64: string, _masks: MaskRect[]): Promise<string> {
  return Promise.reject(new Error('not implemented'));
}
