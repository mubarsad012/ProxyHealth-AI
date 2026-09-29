// Web: the quick-sheet HTML only feeds the browser print dialog (`Print.printAsync`); the PDF
// itself comes from the server with Noto embedded. No font bytes are loaded here — the HTML
// declares local() faces and the browser falls back to its own fonts for every script.

import type { QuickSheetFontFace } from './html';

export async function loadQuickSheetFonts(_fontHint: string | null): Promise<QuickSheetFontFace[]> {
  return [];
}
