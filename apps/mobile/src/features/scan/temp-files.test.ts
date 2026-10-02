// Native capture temp files (PRODUCT_SPEC S6 err.internal / err.timeout "Your paper was not saved
// anywhere", D-22): a camera / picker / document-picker original under `Paths.cache/<Module>/` and
// the image-manipulator output are deleted as soon as the compressed base64 exists, and the
// session's page is swapped to that data first. Nothing outside those cache folders is touched.

import type { CapturedPage } from '@/store/session';
import { useSession } from '@/store/session';
import { preparePages } from '@/features/analysis/buildRequest';
import { CAPTURE_TEMP_DIRS, deleteCaptureTemp, isCaptureTempUri, toJpegBase64 } from '@/lib/image';

import { pagesToPrepare, prepareArrivedPages } from './arrival';
import { compressPage, discardPageFiles, isCompressed, turnPage } from './compress';
import { refusedPages } from './CaptureScreen';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const mockFiles = new Set<string>();
const mockDeleted: string[] = [];

jest.mock('expo-file-system', () => ({
  Paths: { cache: { uri: 'file:///data/user/0/app/cache/' } },
  File: class {
    uri: string;
    constructor(uri: string) {
      this.uri = uri;
    }
    get exists() {
      return mockFiles.has(this.uri);
    }
    delete() {
      if (!mockFiles.has(this.uri)) throw new Error('missing');
      mockFiles.delete(this.uri);
      mockDeleted.push(this.uri);
    }
    async base64() {
      if (!mockFiles.has(this.uri)) throw new Error('missing');
      return 'JVBERi0=';
    }
  },
}));

let mockSeq = 0;
const mockReads: string[] = [];
jest.mock('expo-image-manipulator', () => ({
  SaveFormat: { JPEG: 'jpeg' },
  ImageManipulator: {
    manipulate: (uri: string) => {
      const ctx = {
        rotate: () => ctx,
        resize: () => ctx,
        renderAsync: async () => {
          if (!uri.startsWith('data:') && !mockFiles.has(uri)) throw new Error('source deleted');
          mockReads.push(uri);
          return {
            width: 1200,
            height: 1600,
            saveAsync: async () => {
              mockSeq += 1;
              const out = `file:///data/user/0/app/cache/ImageManipulator/out-${mockSeq}.jpg`;
              mockFiles.add(out);
              return { uri: out, base64: 'SlBFRw==', width: 1200, height: 1600 };
            },
          };
        },
      };
      return ctx;
    },
  },
}));

const CACHE = 'file:///data/user/0/app/cache/';

function photo(id: string, uri = `${CACHE}Camera/${id}.jpg`): CapturedPage {
  mockFiles.add(uri);
  return { id, uri, mimeType: 'image/jpeg', width: 3000, height: 4000, rotation: 0, masks: [], source: 'camera' };
}

beforeEach(() => {
  mockFiles.clear();
  mockDeleted.length = 0;
  mockReads.length = 0;
  useSession.getState().reset();
});

describe('which files are temp files', () => {
  it('only files inside the capture folders of the app cache', () => {
    expect(CAPTURE_TEMP_DIRS).toEqual(['Camera', 'ImageManipulator', 'ImagePicker', 'DocumentPicker']);
    for (const dir of CAPTURE_TEMP_DIRS) expect(isCaptureTempUri(`${CACHE}${dir}/a.jpg`, CACHE)).toBe(true);
    expect(isCaptureTempUri(`${CACHE}Print/sheet.pdf`, CACHE)).toBe(false);
    expect(isCaptureTempUri('file:///data/user/0/app/files/vault/doc/p1.jpg', CACHE)).toBe(false);
    expect(isCaptureTempUri(`${CACHE}Camera/`, CACHE)).toBe(false);
    expect(isCaptureTempUri(`${CACHE}Camera/../vault/p1.jpg`, CACHE)).toBe(false);
    expect(isCaptureTempUri('content://media/external/images/1', CACHE)).toBe(false);
    expect(isCaptureTempUri('data:image/jpeg;base64,AAAA', CACHE)).toBe(false);
    expect(isCaptureTempUri(`${CACHE}Camera/a.jpg`, null)).toBe(false);
    // `file://` with or without the third slash, cache URI with or without its trailing slash.
    expect(isCaptureTempUri('file:///var/Caches/ImagePicker/x.jpeg', 'file:///var/Caches')).toBe(true);
  });

  it('deleteCaptureTemp removes a capture file and never anything else', () => {
    const tmp = `${CACHE}ImagePicker/x.jpeg`;
    const vaultFile = 'file:///data/user/0/app/files/vault/doc/p1.jpg';
    mockFiles.add(tmp);
    mockFiles.add(vaultFile);
    expect(deleteCaptureTemp(vaultFile)).toBe(false);
    expect(deleteCaptureTemp(tmp)).toBe(true);
    expect(deleteCaptureTemp(tmp)).toBe(false); // already gone; never throws
    expect(mockDeleted).toEqual([tmp]);
    expect(mockFiles.has(vaultFile)).toBe(true);
  });
});

describe('deleted as soon as the compressed base64 exists', () => {
  it('the manipulator output is deleted right after it is read', async () => {
    const out = await toJpegBase64({ uri: photo('a').uri }, { maxEdge: 1600, quality: 0.8 });
    expect(out.base64).toBe('SlBFRw==');
    expect(mockDeleted).toEqual([`${CACHE}ImageManipulator/out-${mockSeq}.jpg`]);
  });

  it('a camera original is deleted after compression and the session page points at the JPEG data', async () => {
    const p = photo('p1');
    useSession.getState().setPages([p]);
    useSession.getState().updatePage('p1', { masks: [{ x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.2 }] }); // drawn meanwhile
    const out = await compressPage(p);
    expect(out.uri.startsWith('data:image/jpeg;base64,')).toBe(true);
    expect(mockFiles.has(p.uri)).toBe(false);
    expect(mockDeleted).toContain(p.uri);
    const s = useSession.getState().pages[0];
    expect(s.uri).toBe(out.uri);
    expect(s.base64).toBe('SlBFRw==');
    expect(s.masks).toEqual([{ x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.2 }]);
    expect(isCompressed(s)).toBe(true);
    // Compressing it again reads nothing.
    mockReads.length = 0;
    await compressPage(s);
    expect(mockReads).toEqual([]);
  });

  it('two callers share one job, so the original is read once and never after it is gone', async () => {
    const p = photo('p2');
    useSession.getState().setPages([p]);
    const [a, b] = await Promise.all([compressPage(p), compressPage(p)]);
    expect(a).toBe(b);
    expect(mockReads.filter((u) => u === p.uri)).toHaveLength(1);
  });

  it('"Turn" on a fresh capture compresses it once, then turns the JPEG', async () => {
    const p = photo('p3');
    useSession.getState().setPages([p]);
    const turned = await turnPage(p);
    expect(turned.rotation).toBe(0);
    expect(mockFiles.has(p.uri)).toBe(false);
    expect(mockReads.filter((u) => u === p.uri)).toHaveLength(1);
  });

  it('a picked PDF copy is deleted once its base64 is read', async () => {
    const uri = `${CACHE}DocumentPicker/x.pdf`;
    mockFiles.add(uri);
    const pdf: CapturedPage = { id: 'pdf', uri, mimeType: 'application/pdf', rotation: 0, masks: [], source: 'pdf', byteLength: 6 };
    useSession.getState().setPages([pdf]);
    const out = await compressPage(pdf);
    expect(out.base64).toBe('JVBERi0=');
    expect(mockFiles.has(uri)).toBe(false);
    expect(useSession.getState().pages[0].base64).toBe('JVBERi0=');
  });

  it('a page that is not a capture temp file is compressed but never deleted', async () => {
    const uri = 'file:///data/user/0/app/files/vault/doc/p1.jpg';
    mockFiles.add(uri);
    const p: CapturedPage = { id: 'v1', uri, mimeType: 'image/jpeg', rotation: 0, masks: [], source: 'library' };
    await compressPage(p);
    expect(mockFiles.has(uri)).toBe(true);
    expect(pagesToPrepare([p])).toEqual([]);
  });
});

describe('S4/S5 on arrival', () => {
  it('compresses every waiting capture and leaves the rest alone', async () => {
    const a = photo('a1');
    const b = photo('b1', `${CACHE}ImagePicker/b1.jpeg`);
    const kept: CapturedPage = { id: 'd', uri: 'data:image/jpeg;base64,SlBFRw==', base64: 'SlBFRw==', mimeType: 'image/jpeg', rotation: 0, masks: [], source: 'camera' };
    useSession.getState().setPages([a, b, kept]);
    expect(pagesToPrepare(useSession.getState().pages).map((p) => p.id)).toEqual(['a1', 'b1']);
    await prepareArrivedPages(useSession.getState().pages);
    expect(mockFiles.has(a.uri) || mockFiles.has(b.uri)).toBe(false);
    expect(useSession.getState().pages.every(isCompressed)).toBe(true);
    expect(pagesToPrepare(useSession.getState().pages)).toEqual([]);
  });

  it('"Read this paper" while several pages are still compressing never reads a deleted original', async () => {
    const p1 = photo('r1');
    const p2 = photo('r2', `${CACHE}ImagePicker/r2.jpeg`);
    useSession.getState().setPages([p1, p2]);
    // S5 starts the on-arrival pass; the user taps "Read this paper" at once, and useAnalyze hands
    // over its snapshot (still the temp URIs) while page 2's arrival job finishes and deletes it.
    const arrival = prepareArrivedPages([p1, p2]);
    const prepared = await preparePages([p1, p2], 'ios');
    await arrival;
    expect(prepared.inputs).toHaveLength(2);
    expect(prepared.inputs.every((i) => i.data_base64 === 'SlBFRw==')).toBe(true);
    expect(mockReads.filter((u) => u === p1.uri)).toHaveLength(1);
    expect(mockReads.filter((u) => u === p2.uri)).toHaveLength(1);
    expect(mockFiles.has(p1.uri) || mockFiles.has(p2.uri)).toBe(false);
  });

  it('a snapshot taken before the swap still resolves to the JPEG, with its own hidden parts', async () => {
    const p = photo('s1');
    useSession.getState().setPages([p]);
    await prepareArrivedPages([p]);
    expect(mockFiles.has(p.uri)).toBe(false);
    // Boxes drawn while the page was being prepared travel with the stale snapshot.
    const box = { x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.2 };
    mockReads.length = 0;
    const out = await compressPage({ ...p, masks: [box] });
    expect(mockReads).toEqual([]);
    expect(out.base64).toBe('SlBFRw==');
    expect(out.masks).toEqual([box]);
  });

  it('a job joined while it runs keeps the joining caller\'s hidden parts', async () => {
    const p = photo('m1');
    useSession.getState().setPages([p]);
    const box = { x0: 0.2, y0: 0.2, x1: 0.6, y1: 0.4 };
    const arrival = prepareArrivedPages([p]);
    const prepared = await preparePages([{ ...p, masks: [box] }], 'ios');
    await arrival;
    expect(prepared.inputs[0].masks).toEqual([box]);
    expect(mockReads.filter((u) => u === p.uri)).toHaveLength(1);
  });

  it('a removed page, and a pick the page rules refuse, lose their temp files at once', () => {
    const gone = photo('g1');
    discardPageFiles(gone);
    expect(mockFiles.has(gone.uri)).toBe(false);
    const x = photo('x1');
    const y = photo('y1');
    expect(refusedPages([x, y], [x]).map((p) => p.id)).toEqual(['y1']);
  });
});
