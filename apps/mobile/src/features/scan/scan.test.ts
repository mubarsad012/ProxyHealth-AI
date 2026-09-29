// Scan helpers (BUILD_PLAN §5.6; PRODUCT_SPEC S4/S5; D-19, D-21): gesture-safe pickers (the picker
// is invoked synchronously, before any await), page-list rules, mask geometry and rotation.

import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';

import { base64ByteLength, fitWithin, normaliseMask, normaliseRotation, stripDataUrl } from '@/lib/image';
import { checkPdfSize, pdfSizeMb } from '@/lib/pdf';
import type { CapturedPage } from '@/store/session';

import { rotateMasks } from './compress';
import { maskAround, maskFromDrag, moveMask } from './masks';
import { movePage, pagesAfterPick } from './pageQueue';
import { createPickers } from './pick';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-image-picker', () => ({
  launchImageLibraryAsync: jest.fn(),
  launchCameraAsync: jest.fn(),
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn(),
}));

const lib = ImagePicker.launchImageLibraryAsync as jest.Mock;
const cam = ImagePicker.launchCameraAsync as jest.Mock;
const doc = DocumentPicker.getDocumentAsync as jest.Mock;

function img(id: string): CapturedPage {
  return { id, uri: `file:///${id}.jpg`, mimeType: 'image/jpeg', rotation: 0, masks: [], source: 'library' };
}

describe('gesture-safe pickers', () => {
  beforeEach(() => jest.clearAllMocks());

  it('calls the library picker synchronously inside the handler and maps assets', async () => {
    lib.mockResolvedValue({
      canceled: false,
      assets: [{ uri: 'blob:a', width: 1000, height: 1300, mimeType: 'image/png', fileName: 'a.png', fileSize: 1234 }],
    });
    const pickers = createPickers(() => 3);
    const pending = pickers.pickFromLibrary({});
    expect(lib).toHaveBeenCalledTimes(1); // before any await: the browser user-gesture rule
    expect(lib.mock.calls[0][0]).toMatchObject({ mediaTypes: ['images'], allowsMultipleSelection: true, selectionLimit: 3, exif: false });
    const pages = await pending;
    expect(pages).toHaveLength(1);
    expect(pages[0]).toMatchObject({ uri: 'blob:a', mimeType: 'image/png', width: 1000, height: 1300, source: 'library', byteLength: 1234 });
  });

  it('calls the PDF picker synchronously and returns one pdf page', async () => {
    doc.mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///x.pdf', name: 'x.pdf', size: 2048, lastModified: 0 }] });
    const pending = createPickers(() => 12).pickPdf({});
    expect(doc).toHaveBeenCalledWith({ type: 'application/pdf', multiple: false, copyToCacheDirectory: true });
    const page = await pending;
    expect(page).toMatchObject({ mimeType: 'application/pdf', fileName: 'x.pdf', byteLength: 2048, source: 'pdf' });
  });

  it('camera picker and cancel paths', async () => {
    cam.mockResolvedValue({ canceled: true, assets: null });
    const pending = createPickers(() => 12).takePhoto({});
    expect(cam).toHaveBeenCalledTimes(1);
    await expect(pending).resolves.toEqual([]);
  });
});

describe('page-list rules', () => {
  const limits = { max_pages: 3, max_pdf_bytes: 1000 };

  it('adds photos up to the cap and reports the cap', () => {
    const out = pagesAfterPick([img('a'), img('b')], [img('c'), img('d')], limits);
    expect(out.kind).toBe('page_cap');
    expect(out.pages.map((p) => p.id)).toEqual(['a', 'b', 'c']);
  });

  it('refuses mixing photos and a PDF, and a PDF over the byte cap', () => {
    const pdf: CapturedPage = { ...img('p'), mimeType: 'application/pdf', source: 'pdf', byteLength: 500 };
    expect(pagesAfterPick([img('a')], [pdf], limits).kind).toBe('pdf_or_photos');
    expect(pagesAfterPick([pdf], [img('a')], limits).kind).toBe('pdf_or_photos');
    const big = pagesAfterPick([], [{ ...pdf, byteLength: 5000 }], limits);
    expect(big.kind).toBe('too_large');
    expect(pagesAfterPick([], [pdf], limits)).toEqual({ kind: 'ok', pages: [pdf] });
  });

  it('moves pages in document order', () => {
    expect(movePage([img('a'), img('b'), img('c')], 'c', -1).map((p) => p.id)).toEqual(['a', 'c', 'b']);
    expect(movePage([img('a')], 'a', -1).map((p) => p.id)).toEqual(['a']);
  });
});

describe('mask geometry', () => {
  it('normalises drags in either direction and ignores taps', () => {
    expect(maskFromDrag({ x: 300, y: 40 }, { x: 100, y: 20 }, { width: 400, height: 400 })).toEqual({ x0: 0.25, y0: 0.05, x1: 0.75, y1: 0.1 });
    expect(maskFromDrag({ x: 10, y: 10 }, { x: 11, y: 11 }, { width: 400, height: 400 })).toBeNull();
  });

  it('places a tap box inside the page and moves it without leaving the page', () => {
    const m = maskAround({ x: 0.99, y: 0.0 });
    expect(m.x1).toBeLessThanOrEqual(1);
    expect(m.y0).toBeGreaterThanOrEqual(0);
    const moved = moveMask(m, 0.5, 0.5);
    expect(moved.x1).toBeLessThanOrEqual(1);
    expect(moved.y1).toBeLessThanOrEqual(1);
  });

  it('rotates masks with the page (90° clockwise)', () => {
    expect(rotateMasks([{ x0: 0.1, y0: 0.2, x1: 0.3, y1: 0.4 }], 90)).toEqual([{ x0: 0.6, y0: 0.1, x1: 0.8, y1: 0.3 }]);
    const full = rotateMasks([{ x0: 0.1, y0: 0.2, x1: 0.3, y1: 0.4 }], 360)[0];
    expect(full).toEqual({ x0: 0.1, y0: 0.2, x1: 0.3, y1: 0.4 });
  });

  it('clamps and orders raw masks', () => {
    expect(normaliseMask({ x0: 1.2, y0: 0.5, x1: 0.8, y1: -1 })).toEqual({ x0: 0.8, y0: 0, x1: 1, y1: 0.5 });
  });
});

describe('image / pdf helpers', () => {
  it('fits the 1600 px cap without upscaling', () => {
    expect(fitWithin(3200, 2400, 1600)).toEqual({ width: 1600, height: 1200 });
    expect(fitWithin(800, 600, 1600)).toEqual({ width: 800, height: 600 });
  });

  it('computes base64 byte length and strips data URLs', () => {
    expect(base64ByteLength('QUJD')).toBe(3);
    expect(base64ByteLength('data:image/jpeg;base64,QUI=')).toBe(2);
    expect(stripDataUrl('data:image/png;base64,AAAA')).toBe('AAAA');
    expect(normaliseRotation(-90)).toBe(270);
  });

  it('checks the PDF byte cap before upload', () => {
    expect(checkPdfSize(13 * 1024 * 1024, { max_pdf_bytes: 12 * 1024 * 1024 })?.code).toBe('payload_too_large');
    expect(checkPdfSize(1024, null)).toBeNull();
    expect(pdfSizeMb(2.34 * 1024 * 1024)).toBe('2.3');
  });
});
