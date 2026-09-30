// Quick-sheet HTML for expo-print (PRODUCT_SPEC S15, ARCHITECTURE §3.1 "PDF / share flows").
// Native: `Print.printToFileAsync({ html })` renders this in a WebView, which cannot see bundled
// app fonts, so the Noto faces are embedded as base64 data URIs (`fontData.*`). Web: the same HTML
// feeds `Print.printAsync` (the browser print dialog). `dir` is set on <html>; English section
// headings stay LTR; phone numbers, dates and other Latin/digit runs are LTR-isolated in RTL.
// Pure: no I/O here, so it is unit-tested directly.

import type { QuickSheetText } from './build';

export interface QuickSheetFontFace {
  /** CSS family name, e.g. `NotoNaskhArabic`. */
  family: string;
  weight: 400 | 700;
  /** `data:font/ttf;base64,…` (embedded) or a URL the renderer can load. */
  src: string;
}

export interface QuickSheetHtmlOptions {
  dir: 'ltr' | 'rtl';
  /** BCP-47 tag of the sheet's language. */
  lang: string;
  /** Primary family (the pack's `font_hint`), when one is bundled. */
  fontFamily?: string | null;
  fontFaces?: QuickSheetFontFace[];
}

const LATIN_FAMILY = 'NotoSans';

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Escape, then (RTL only) wrap Latin/digit runs so numbers and phones read left-to-right. Persian
 * and Arabic-Indic digits count too: after Arabic letters UAX #9 makes digits Arabic numbers and the
 * hyphens between them run right-to-left ("۲۰۲۶-۱۰-۱۴" would show as "۱۴-۱۰-۲۰۲۶"). A leading "+",
 * "(" or currency sign belongs to the run ("$1,240.00" keeps its "$" on the left). Same rule as the
 * PDF (`quicksheet/render.py` `LTR_RUN_RE`).
 */
const LTR_RUN =
  /[+(]?[$€£¥]?[0-9A-Za-z\u0660-\u0669\u06f0-\u06f9](?:[0-9A-Za-z\u0660-\u0669\u06f0-\u06f9$€£¥ .,:/()+\-–&#@']*[0-9A-Za-z\u0660-\u0669\u06f0-\u06f9)])?/g;

export function isolateLtrRuns(text: string, dir: 'ltr' | 'rtl'): string {
  if (dir === 'ltr') return escapeHtml(text);
  let out = '';
  let last = 0;
  for (const m of text.matchAll(LTR_RUN)) {
    const start = m.index ?? 0;
    out += escapeHtml(text.slice(last, start));
    out += `<bdi dir="ltr">${escapeHtml(m[0])}</bdi>`;
    last = start + m[0].length;
  }
  return out + escapeHtml(text.slice(last));
}

function cssString(value: string): string {
  return `"${value.replace(/["\\]/g, '')}"`;
}

export function fontFaceCss(faces: QuickSheetFontFace[]): string {
  return faces
    .map(
      (f) =>
        `@font-face { font-family: ${cssString(f.family)}; font-weight: ${f.weight}; font-style: normal; ` +
        `src: local(${cssString(`${f.family}${f.weight === 700 ? '-Bold' : '-Regular'}`)}), url(${cssString(f.src)}) format("truetype"); }`,
    )
    .join('\n');
}

/** A fallback `@font-face` that names the bundled families locally when no data was loaded. */
function localOnlyFaces(families: string[]): string {
  return families
    .flatMap((family) =>
      ([400, 700] as const).map(
        (w) =>
          `@font-face { font-family: ${cssString(family)}; font-weight: ${w}; ` +
          `src: local(${cssString(`${family}${w === 700 ? '-Bold' : '-Regular'}`)}); }`,
      ),
    )
    .join('\n');
}

export function buildQuickSheetHtml(sheet: QuickSheetText, opts: QuickSheetHtmlOptions): string {
  const dir = opts.dir === 'rtl' ? 'rtl' : 'ltr';
  const primary = opts.fontFamily || LATIN_FAMILY;
  const families = Array.from(new Set([primary, LATIN_FAMILY]));
  const faces = opts.fontFaces ?? [];
  const faceCss = faces.length ? fontFaceCss(faces) : localOnlyFaces(families);
  const stack = `${families.map(cssString).join(', ')}, system-ui, sans-serif`;
  const align = dir === 'rtl' ? 'right' : 'left';
  const sections = sheet.sections
    .map((s) => {
      const en =
        s.heading_en && s.heading_en !== s.heading
          ? `<p class="en" dir="ltr" lang="en">${escapeHtml(s.heading_en)}</p>`
          : '';
      const lines = s.lines.map((l) => `<p class="line">${isolateLtrRuns(l, dir)}</p>`).join('\n');
      return `<section>\n<h2>${isolateLtrRuns(s.heading, dir)}</h2>\n${en}\n${lines}\n</section>`;
    })
    .join('\n');
  return `<!DOCTYPE html>
<html lang="${escapeHtml(opts.lang)}" dir="${dir}">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${escapeHtml(sheet.title)}</title>
<style>
${faceCss}
html, body { margin: 0; padding: 0; background: #FFFFFF; color: #14202B; }
body { font-family: ${stack}; font-size: 13pt; line-height: 1.5; text-align: ${align}; padding: 24pt; }
h1 { font-size: 20pt; font-weight: 700; margin: 0 0 12pt; }
h2 { font-size: 15pt; font-weight: 700; margin: 16pt 0 0; }
p { margin: 2pt 0; }
.en { font-family: ${cssString(LATIN_FAMILY)}, system-ui, sans-serif; color: #3E4C5A; font-size: 11pt; text-align: left; margin-bottom: 4pt; }
bdi { unicode-bidi: isolate; direction: ltr; }
section { page-break-inside: avoid; border-top: 1px solid #D5DCE3; padding-top: 4pt; }
footer { margin-top: 20pt; border-top: 1px solid #7A8794; padding-top: 6pt; font-size: 10pt; color: #3E4C5A; }
</style>
</head>
<body>
<h1>${isolateLtrRuns(sheet.title, dir)}</h1>
${sections}
<footer>${isolateLtrRuns(sheet.footer, dir)}</footer>
</body>
</html>
`;
}
