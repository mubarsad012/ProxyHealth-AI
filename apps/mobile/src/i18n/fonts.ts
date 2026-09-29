// expo-font loading map for the nine bundled Noto families (D-26, PRODUCT_SPEC §5.1 Fonts row).
// Metro needs static `require` calls, so every file is listed by hand; the family keys equal
// `tokens.fonts.<hint>.regular|bold` and the `font_hint` values in `data/languages.yaml`.
// The same files are linked natively by the `expo-font` config plugin in app.json; `useFonts`
// covers web and Expo Go.
//
// Verified against https://docs.expo.dev/versions/v57.0.0/sdk/font/ : `useFonts(map) → [loaded, error]`.

import { useFonts } from 'expo-font';

import { fontForHint, fonts, type FontFamilyToken, type FontHint } from '@/design/tokens';

export const fontAssets: Record<string, number> = {
  'NotoSans-Regular': require('../../assets/fonts/NotoSans-Regular.ttf'),
  'NotoSans-Bold': require('../../assets/fonts/NotoSans-Bold.ttf'),
  'NotoNaskhArabic-Regular': require('../../assets/fonts/NotoNaskhArabic-Regular.ttf'),
  'NotoNaskhArabic-Bold': require('../../assets/fonts/NotoNaskhArabic-Bold.ttf'),
  'NotoNastaliqUrdu-Regular': require('../../assets/fonts/NotoNastaliqUrdu-Regular.ttf'),
  'NotoNastaliqUrdu-Bold': require('../../assets/fonts/NotoNastaliqUrdu-Bold.ttf'),
  'NotoSansEthiopic-Regular': require('../../assets/fonts/NotoSansEthiopic-Regular.ttf'),
  'NotoSansEthiopic-Bold': require('../../assets/fonts/NotoSansEthiopic-Bold.ttf'),
  'NotoSansMyanmar-Regular': require('../../assets/fonts/NotoSansMyanmar-Regular.ttf'),
  'NotoSansMyanmar-Bold': require('../../assets/fonts/NotoSansMyanmar-Bold.ttf'),
  'NotoSansDevanagari-Regular': require('../../assets/fonts/NotoSansDevanagari-Regular.ttf'),
  'NotoSansDevanagari-Bold': require('../../assets/fonts/NotoSansDevanagari-Bold.ttf'),
  'NotoSansBengali-Regular': require('../../assets/fonts/NotoSansBengali-Regular.ttf'),
  'NotoSansBengali-Bold': require('../../assets/fonts/NotoSansBengali-Bold.ttf'),
  'NotoSansGurmukhi-Regular': require('../../assets/fonts/NotoSansGurmukhi-Regular.ttf'),
  'NotoSansGurmukhi-Bold': require('../../assets/fonts/NotoSansGurmukhi-Bold.ttf'),
  'NotoSansHanifiRohingya-Regular': require('../../assets/fonts/NotoSansHanifiRohingya-Regular.ttf'),
  'NotoSansHanifiRohingya-Bold': require('../../assets/fonts/NotoSansHanifiRohingya-Bold.ttf'),
};

/** The relative paths app.json's `expo-font` plugin lists (kept here so both stay in sync). */
export const fontFilePaths: readonly string[] = Object.values(fonts).flatMap((f: FontFamilyToken) => [
  `./assets/fonts/${f.file.regular}`,
  `./assets/fonts/${f.file.bold}`,
]);

export const DEFAULT_FONT_HINT: FontHint = 'NotoSans';

/** Load every bundled family once at the root; returns `[loaded, error]` like `useFonts`. */
export function useAppFonts(): [boolean, Error | null] {
  return useFonts(fontAssets);
}

/** Font family name for a pack `font_hint`; `undefined` → system font (CJK, unknown hints). */
export function fontFamilyFor(
  hint: string | null | undefined,
  weight: 'regular' | 'bold' = 'regular',
): string | undefined {
  const token = fontForHint(hint);
  if (!token) return undefined;
  return weight === 'bold' ? token.bold : token.regular;
}

/** Line height for a base size under a pack's script (Nastaliq needs 2.0 — PRODUCT_SPEC §5.1). */
export function lineHeightFor(hint: string | null | undefined, baseLineHeight: number): number {
  const token = fontForHint(hint);
  return Math.round(baseLineHeight * (token?.lineHeightFactor ?? 1));
}
