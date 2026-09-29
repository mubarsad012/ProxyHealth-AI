// Type declaration for the platform-resolved font loader. Metro picks `fontData.native.ts` on
// iOS/Android (base64 data URIs for expo-print's WebView) and `fontData.web.ts` on web; TypeScript
// resolves `./fontData` to this file. Both implementations export exactly these names.

import type { QuickSheetFontFace } from './html';

/** Regular + bold faces for the pack's `font_hint` and NotoSans (English headings). */
export declare function loadQuickSheetFonts(fontHint: string | null): Promise<QuickSheetFontFace[]>;
