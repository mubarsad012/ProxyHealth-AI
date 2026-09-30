// Quick sheet seam (BUILD_PLAN §4.2; PRODUCT_SPEC S15). Owner: WP6 lane 6B.
// `QuickSheetScreen` is rendered by `app/result/[id]/quicksheet.tsx` (WP5 route); the builder is
// pure and shared with the Action Hub.

export { QuickSheetScreen, type QuickSheetScreenProps } from './QuickSheetScreen';
export {
  buildQuickSheetText,
  quickSheetPlainText,
  toQuickSheetRequest,
  type BuildQuickSheetOptions,
  type QuickSheetMeta,
  type QuickSheetSectionKind,
  type QuickSheetText,
  type TranslateFn,
} from './build';
export { buildQuickSheetHtml, type QuickSheetFontFace, type QuickSheetHtmlOptions } from './html';
export { downloadServerPdf, QUICKSHEET_PDF_FILENAME } from './serverPdf';
export { canShareFiles, copyQuickSheetText, printHtmlInFrame, printQuickSheet, shareQuickSheetPdf } from './share';
