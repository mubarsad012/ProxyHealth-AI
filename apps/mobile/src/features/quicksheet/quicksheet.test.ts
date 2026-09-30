// WP6 quick-sheet tests (BUILD_PLAN §5.7 step 3): the text builder drops a stripped contact and
// never adds anything that is not in the analysis or the resource DB; the expo-print HTML carries
// `dir="rtl"` and an embedded `@font-face`.

import { render } from '@testing-library/react-native';
import { type ComponentType, createElement, type ReactNode } from 'react';

import type { ApiClient } from '@/api/client';
import { ApiError } from '@/api/errors';
import type { AnalysisResult, Resource } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { telHref } from '@/features/help/format';
import { clearMatchCache } from '@/features/help/request';
import { BASE_STRINGS, bundledPackFor, translate } from '@/i18n/store';
import { translateForLayout } from '@/i18n/useT';

import { buildQuickSheetText, quickSheetPlainText, toQuickSheetRequest } from './build';
import { buildAllowList, formatPhone, scrubLine } from './contacts';
import { buildQuickSheetHtml, isolateLtrRuns } from './html';
import { QuickSheetScreen } from './QuickSheetScreen';
import { printHtmlInFrame } from './share';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
// The expo-network jest mock's listener has no `remove()`; reachability is not under test here.
jest.mock('@/lib/network', () => ({ useOnline: () => ({ online: true, known: true }), isOnline: async () => true }));

const medicaid = require('../../../assets/fixtures/medicaid_address_confirmation.result.en.json') as AnalysisResult;
const fallbacks = require('../../../assets/resources/national_fallbacks.json') as Resource[];

const t = (key: string, vars?: Record<string, string | number>) => translate(BASE_STRINGS, key, vars);
const MARKER = BASE_STRINGS['warning.contacts_stripped_inline'];
const r211 = fallbacks.find((r) => r.id === '211') as Resource;
const rImm = fallbacks.find((r) => r.id === 'immlawhelp') as Resource;

function withStrippedContact(): AnalysisResult {
  const a: AnalysisResult = JSON.parse(JSON.stringify(medicaid));
  a.plan_steps = [
    ...a.plan_steps,
    { id: 's9', kind: 'call', demand_id: null, resource_tags: [], span_ids: [], text: `Call ${MARKER} for help.` },
    { id: 's10', kind: 'call', demand_id: null, resource_tags: [], span_ids: [], text: MARKER },
  ];
  a.questions_to_ask = [...a.questions_to_ask, 'Can I call 703-555-0199 or visit fakehelp.org?'];
  return a;
}

describe('buildQuickSheetText', () => {
  it('drops a stripped contact marker and never re-adds contacts', () => {
    const sheet = buildQuickSheetText(withStrippedContact(), [r211], t, { today: '2026-09-27' });
    const text = quickSheetPlainText(sheet);
    expect(text).not.toContain(MARKER);
    expect(text).not.toContain('contact removed');
    // Invented phone / domain (not on the paper, not in the DB) are removed from the line.
    expect(text).not.toContain('703-555-0199');
    expect(text).not.toContain('fakehelp.org');
    // The rest of the sentence survives; a line that was only a marker is gone.
    expect(text).toContain('Call for help.');
    const plan = sheet.sections[sheet.sectionKinds!.indexOf('plan')];
    expect(plan.lines.every((l) => l.trim().length > 3)).toBe(true);
  });

  it('keeps contacts that are on the paper and DB phones only', () => {
    const a = withStrippedContact();
    a.original_text[0].blocks.push({
      bbox: [0, 0, 1, 1], id: 'p1b99', is_handwriting: false, is_unclear: false, page: 1, text: 'Call 1-855-242-8282',
    });
    a.questions_to_ask = ['Should I call 855-242-8282?'];
    const sheet = buildQuickSheetText(a, [r211, rImm], t, { today: '2026-09-27' });
    const text = quickSheetPlainText(sheet);
    expect(text).toContain('855-242-8282');
    const help = sheet.sections[sheet.sectionKinds!.indexOf('help')];
    expect(help.heading).toBe('Who can help');
    expect(help.lines[0]).toBe(`211 — ${formatPhone('211')}`);
    expect(sheet.resources).toEqual([
      { name: r211.name, phone: r211.phone, url: r211.url },
      { name: rImm.name, phone: rImm.phone ?? null, url: rImm.url },
    ]);
  });

  it('builds localized headings with English under them, title suffix and footer date', () => {
    const sheet = buildQuickSheetText(medicaid, [], t, { today: '2026-09-27' });
    expect(sheet.title).toBe('Medicaid asks you to confirm your address — quick sheet');
    expect(sheet.footer).toContain('2026-09-27');
    expect(sheet.sections[0]).toMatchObject({ heading: 'What is this?', heading_en: 'What is this?' });
    const dates = sheet.sections[sheet.sectionKinds!.indexOf('dates')];
    expect(dates.lines.join(' ')).toContain('October 14, 2026');
    expect(sheet.sectionKinds).not.toContain('help');
    const bring = sheet.sections[sheet.sectionKinds!.indexOf('bring')];
    expect(bring.lines).toContain('the enclosed form');
  });

  it('caps lines at 40 with the truncation line and sends resources outside sections', () => {
    const a: AnalysisResult = JSON.parse(JSON.stringify(medicaid));
    a.questions_to_ask = Array.from({ length: 60 }, (_, i) => `Question number ${i + 1} about this letter?`);
    const sheet = buildQuickSheetText(a, [r211], t, { today: '2026-09-27' });
    const q = sheet.sections[sheet.sectionKinds!.indexOf('questions')];
    expect(q.lines).toHaveLength(40);
    expect(q.lines[39]).toBe(BASE_STRINGS['quicksheet.truncated']);
    const req = toQuickSheetRequest(sheet, { languageTag: 'en', direction: 'ltr', fontHint: 'NotoSans', generatedOn: '2026-09-27' });
    expect(req.sections.length).toBeLessThanOrEqual(8);
    // "Who can help" travels as a heading carrier (no lines); the server draws the resources.
    const carrier = req.sections.find((s) => s.heading_en === 'Who can help');
    expect(carrier).toEqual({ heading: 'Who can help', heading_en: 'Who can help', lines: [] });
    expect(req.resources).toEqual([{ name: '211', phone: '211', url: r211.url }]);
    expect(req.generated_on).toBe('2026-09-27');
  });

  it('sends the localized "Who can help" heading and no UI bidi isolates (Dari)', () => {
    const prs = bundledPackFor('prs')!;
    const tPrs = (key: string, vars?: Record<string, string | number>) => translateForLayout(prs.strings, 'rtl', key, vars);
    const sheet = buildQuickSheetText(JSON.parse(JSON.stringify(medicaid)), [r211], tPrs, { today: '2026-09-27' });
    const req = toQuickSheetRequest(sheet, { languageTag: 'prs', direction: 'rtl', fontHint: 'NotoNaskhArabic' });
    const carrier = req.sections.find((s) => s.heading_en === 'Who can help');
    expect(carrier).toEqual({ heading: prs.strings['quicksheet.help'], heading_en: 'Who can help', lines: [] });
    const all = [req.title, req.footer, ...req.sections.flatMap((s) => [s.heading, s.heading_en, ...s.lines])];
    expect(all.some((x) => /[\u2066-\u2069]/.test(x))).toBe(false);
  });

  it('with no resources there is no carrier', () => {
    const sheet = buildQuickSheetText(JSON.parse(JSON.stringify(medicaid)), [], t, { today: '2026-09-27' });
    const req = toQuickSheetRequest(sheet, { languageTag: 'en', direction: 'ltr', fontHint: 'NotoSans' });
    expect(req.sections.map((s) => s.heading_en)).not.toContain('Who can help');
    expect(req.resources).toEqual([]);
  });
});

describe('formatPhone', () => {
  it('prints US numbers readably and keeps every national digit', () => {
    expect(formatPhone('+18003182596')).toBe('1-800-318-2596');
    expect(formatPhone('+18558894325')).toBe('1-855-889-4325');
    expect(formatPhone('+15714725880')).toBe('(571) 472-5880');
    expect(formatPhone('211')).toBe('211');
    expect(formatPhone('988')).toBe('988');
    expect(formatPhone('+442071234567')).toBe('+442071234567');
    for (const r of fallbacks) {
      for (const phone of [r.phone, r.tty]) {
        if (!phone) continue;
        const printed = formatPhone(phone);
        const digits = phone.replace(/\D/g, '');
        expect(printed.replace(/\D/g, '').endsWith(digits.length >= 10 ? digits.slice(-10) : digits)).toBe(true);
      }
    }
  });

  it('tel: links keep the stored E.164 value', () => {
    expect(telHref('+18003182596')).toBe('tel:+18003182596');
    expect(telHref('211')).toBe('tel:211');
  });
});

describe('scrubLine', () => {
  it('does not treat dates or receipt numbers as phones', () => {
    const allow = buildAllowList('', []);
    expect(scrubLine('Reply by 10-14-2026.', allow, [])).toBe('Reply by 10-14-2026.');
    expect(scrubLine('Receipt IOE0912345678 is yours.', allow, [])).toBe('Receipt IOE0912345678 is yours.');
    expect(scrubLine('Call (571) 555-0142 today.', allow, [])).toBe('Call today.');
  });
});

describe('buildQuickSheetHtml', () => {
  const sheet = {
    title: 'نامه مدیکید — برگه سریع',
    sections: [{ heading: 'این چیست؟', heading_en: 'What is this?', lines: ['تا October 14, 2026 جواب بدهید.', 'Call 211'] }],
    footer: 'ساخته شده با کامپیوتر. 2026-09-27',
  };

  it('sets dir="rtl", embeds @font-face data URIs and keeps English headings LTR', () => {
    const html = buildQuickSheetHtml(sheet, {
      dir: 'rtl',
      lang: 'prs',
      fontFamily: 'NotoNaskhArabic',
      fontFaces: [
        { family: 'NotoNaskhArabic', weight: 400, src: 'data:font/ttf;base64,AAEAAAAL' },
        { family: 'NotoSans', weight: 400, src: 'data:font/ttf;base64,AAEAAAAM' },
      ],
    });
    expect(html).toContain('dir="rtl"');
    expect(html).toContain('lang="prs"');
    expect(html).toContain('@font-face');
    expect(html).toContain('data:font/ttf;base64,AAEAAAAL');
    expect(html).toContain('<p class="en" dir="ltr" lang="en">What is this?</p>');
    expect(html).toContain('<bdi dir="ltr">October 14, 2026</bdi>');
  });

  it('still declares @font-face (local names) when no font data could be loaded', () => {
    const html = buildQuickSheetHtml(sheet, { dir: 'ltr', lang: 'en' });
    expect(html).toContain('dir="ltr"');
    expect(html).toContain('@font-face');
  });

  it('isolates Persian-digit dates and phones inside Dari lines', () => {
    expect(isolateLtrRuns('تا ۲۰۲۶-۱۰-۱۴ جواب بدهید', 'rtl')).toBe('تا <bdi dir="ltr">۲۰۲۶-۱۰-۱۴</bdi> جواب بدهید');
    expect(isolateLtrRuns('به 1-800-318-2596 زنگ بزنید', 'rtl')).toBe('به <bdi dir="ltr">1-800-318-2596</bdi> زنگ بزنید');
  });

  it('keeps a leading currency sign inside the amount isolate (Inova Dari demand line)', () => {
    // assets/fixtures/inova_final_notice.result.prs.json: without the "$" inside the <bdi> it shows as "1,240.00$".
    const inova = 'می‌گوید مبلغ قابل پرداخت $1,240.00 تا ۲۸ اکتبر ۲۰۲۶ است.';
    const html = isolateLtrRuns(inova, 'rtl');
    expect(html).toContain('<bdi dir="ltr">$1,240.00</bdi>');
    expect(html).not.toContain('$<bdi');
    expect(isolateLtrRuns('مبلغ: $125.00', 'rtl')).toBe('مبلغ: <bdi dir="ltr">$125.00</bdi>');
    expect(isolateLtrRuns('از (571) 472-5880 بپرسید', 'rtl')).toBe('از <bdi dir="ltr">(571) 472-5880</bdi> بپرسید');
  });

  it('escapes markup in lines', () => {
    expect(isolateLtrRuns('<b>x</b> & "y"', 'rtl')).not.toContain('<b>');
    expect(isolateLtrRuns('a & b', 'ltr')).toBe('a &amp; b');
  });
});

function offlineClient(): ApiClient {
  const fail = () => Promise.reject(new ApiError({ code: 'network', status: 0 }));
  return {
    baseUrl: 'http://127.0.0.1:8029',
    health: fail,
    getConfig: fail,
    getPack: fail,
    postPack: fail,
    analyze: fail,
    troubleshoot: fail,
    chat: fail,
    matchResources: fail,
    listResources: fail,
    getResource: fail,
    getRules: fail,
    quicksheetPdf: fail,
    feedback: fail,
    listFixtures: fail,
    fixturePageUrl: (id, n) => `http://127.0.0.1:8029/v1/demo/fixtures/${id}/pages/${n}`,
  };
}

// `.ts` file (no JSX): children go in createElement's third argument, so relax the props type.
const Providers = AppProviders as ComponentType<{ client: ApiClient; staticMetrics?: boolean; children?: ReactNode }>;

describe('QuickSheetScreen', () => {
  beforeEach(() => clearMatchCache());

  it('offline with no list for this paper uses the bundled DB subset for "Who can help"', async () => {
    const { findByText, getByTestId } = await render(
      createElement(Providers, { client: offlineClient(), staticMetrics: true }, createElement(QuickSheetScreen, { analysis: medicaid })),
    );
    expect(await findByText('Who can help', {}, { timeout: 4000 })).toBeTruthy();
    expect(await findByText(`211 — ${formatPhone('211')}`)).toBeTruthy();
    expect(getByTestId('quicksheet-copy')).toBeTruthy();
  });

  it('web print helper is a no-op off the web (native uses expo-print)', () => {
    expect(printHtmlInFrame('<html></html>', null)).toBe(false);
  });
});
