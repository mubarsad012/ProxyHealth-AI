// Native: embed the bundled Noto TTFs as base64 data URIs so expo-print's WebView renders the
// pack's script (PRODUCT_SPEC S15, ARCHITECTURE §3.1). Asset URIs come from React Native's asset
// registry (`Image.resolveAssetSource`): http(s) in development (Metro), file:// on iOS release.
// Android release assets have no readable URI; there the expo-font config plugin has copied the
// files to the APK's assets/fonts, which the WebView can load directly.

import { File } from 'expo-file-system';
import { Image, Platform } from 'react-native';

import { fontForHint } from '@/design/tokens';
import { fontAssets } from '@/i18n/fonts';

import { bytesToBase64 } from './base64';
import type { QuickSheetFontFace } from './html';

const cache = new Map<string, string>();

async function srcFor(face: string, file: string): Promise<string | null> {
  const hit = cache.get(face);
  if (hit) return hit;
  const mod = fontAssets[face];
  if (mod === undefined) return null;
  let src: string | null = null;
  try {
    const uri = Image.resolveAssetSource(mod)?.uri ?? '';
    if (/^https?:/i.test(uri)) {
      const res = await fetch(uri);
      src = `data:font/ttf;base64,${bytesToBase64(new Uint8Array(await res.arrayBuffer()))}`;
    } else if (uri.startsWith('file:')) {
      src = `data:font/ttf;base64,${await new File(uri).base64()}`;
    } else if (Platform.OS === 'android') {
      src = `file:///android_asset/fonts/${file}`;
    }
  } catch {
    src = Platform.OS === 'android' ? `file:///android_asset/fonts/${file}` : null;
  }
  if (src) cache.set(face, src);
  return src;
}

export async function loadQuickSheetFonts(fontHint: string | null): Promise<QuickSheetFontFace[]> {
  const families = Array.from(new Set([fontForHint(fontHint) ? fontHint : null, 'NotoSans'].filter(Boolean))) as string[];
  const faces: QuickSheetFontFace[] = [];
  for (const family of families) {
    const token = fontForHint(family);
    if (!token) continue;
    for (const [weight, face, file] of [
      [400, token.regular, token.file.regular],
      [700, token.bold, token.file.bold],
    ] as const) {
      const src = await srcFor(face, file);
      if (src) faces.push({ family, weight, src });
    }
  }
  return faces;
}
