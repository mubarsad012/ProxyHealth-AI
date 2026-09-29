// Screenshot picker for S16 (one image, never a PDF). Gesture rule (BUILD_PLAN §1.1 rule 7,
// expo.md warnings): on web the browser file dialog only opens from a user gesture, so
// `pickScreenshot()` starts `launchImageLibraryAsync` as its very first statement and callers
// invoke it as the first statement of `onPress`. After the pick the image is re-encoded to JPEG
// (≤ 1600 px, quality 0.8, EXIF dropped) — via WP5's `toJpegBase64` when available, otherwise
// expo-image-manipulator (which has a web implementation). Nothing is written to disk.

import * as ImageManipulator from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';

import type { PageInput } from '@/api/types';
import { toJpegBase64 } from '@/lib/image';

export const MAX_EDGE = 1600;
export const JPEG_QUALITY = 0.8;

export type ScreenshotMime = 'image/jpeg' | 'image/png' | 'image/webp';

export interface Screenshot {
  /** Preview URI (file://, blob: or data:). */
  uri: string;
  base64: string;
  mimeType: ScreenshotMime;
  width: number;
  height: number;
}

const RAW_OK: ReadonlySet<string> = new Set(['image/jpeg', 'image/png', 'image/webp']);

export function resizeFor(width: number, height: number): { width?: number; height?: number } | null {
  if (!width || !height || Math.max(width, height) <= MAX_EDGE) return null;
  return width >= height ? { width: MAX_EDGE } : { height: MAX_EDGE };
}

async function viaManipulator(asset: ImagePicker.ImagePickerAsset): Promise<Screenshot> {
  const ctx = ImageManipulator.ImageManipulator.manipulate(asset.uri);
  const resize = resizeFor(asset.width, asset.height);
  if (resize) ctx.resize(resize);
  const image = await ctx.renderAsync();
  const saved = await image.saveAsync({ compress: JPEG_QUALITY, format: ImageManipulator.SaveFormat.JPEG, base64: true });
  if (!saved.base64) throw new Error('no image data');
  return { uri: saved.uri, base64: saved.base64, mimeType: 'image/jpeg', width: saved.width, height: saved.height };
}

export async function toScreenshot(asset: ImagePicker.ImagePickerAsset): Promise<Screenshot> {
  const input = Platform.OS === 'web' && asset.file ? { file: asset.file } : { uri: asset.uri };
  try {
    const jpeg = await toJpegBase64(input, { maxEdge: MAX_EDGE, quality: JPEG_QUALITY });
    return { uri: asset.uri, base64: jpeg.base64, mimeType: 'image/jpeg', width: jpeg.width, height: jpeg.height };
  } catch {
    // WP5 helper not available yet (seam stub) or failed: fall through.
  }
  try {
    return await viaManipulator(asset);
  } catch (e) {
    // Last resort on web: the picker already read the original bytes.
    const mime = asset.mimeType ?? '';
    if (asset.base64 && RAW_OK.has(mime)) {
      return { uri: asset.uri, base64: asset.base64, mimeType: mime as ScreenshotMime, width: asset.width, height: asset.height };
    }
    throw e;
  }
}

/** Call as the FIRST statement of the button's onPress. Resolves null when cancelled. */
export function pickScreenshot(): Promise<Screenshot | null> {
  const launched = ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsMultipleSelection: false,
    allowsEditing: false,
    quality: 1,
    exif: false,
    base64: Platform.OS === 'web',
  });
  return launched.then((res) => {
    const asset = res.canceled ? null : res.assets?.[0];
    if (!asset || (asset.type && asset.type !== 'image')) return null;
    return toScreenshot(asset);
  });
}

export function toPageInput(shot: Screenshot): PageInput {
  return { mime_type: shot.mimeType, data_base64: shot.base64, masks: [], rotation: 0 };
}
