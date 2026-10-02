// Phase 2C: saving a paper whose first page has "Hide parts" boxes (native: the boxes are not in
// the pixels, so that page keeps no image, D-19) still keeps the later pages, and reading them back
// keeps every page at its own number (page 2 is never shown as page 1).

import type { AnalysisResult } from '@/api/types';
import type { StoredPage, StoredPageInput, Vault } from '@/storage/index';
import type { CapturedPage } from '@/store/session';

import { buildStoredDocument } from './documents';
import { isPageGap, loadStoredPageSlots } from './pages';

const t = (key: string) => key;
const page = (n: number, masks: CapturedPage['masks'] = []): CapturedPage => ({
  id: `s${n}`,
  uri: `file:///session/${n}.jpg`,
  base64: `/9j/PAGE${n}`,
  mimeType: 'image/jpeg',
  rotation: 0,
  masks,
  source: 'camera',
});
const analysis = {
  analysis_id: 'an_masks',
  category: 'benefits',
  document_type: 'medicaid_renewal',
  demands: [],
  unverified: [],
  summary: { title: 'Medicaid letter', body: '', body_en: '', span_ids: [] },
  quality: { legibility: 'good', pages_received: 3, pages_unreadable: [], readable: true, reason: null },
  model_meta: { demo: false },
  page_thumbnails: null,
} as unknown as AnalysisResult;

function vaultWith(inputs: StoredPageInput[], missing: number[] = []): Vault {
  const rows: StoredPage[] = inputs.map((p) => ({ documentId: 'an_masks', page: p.page, filePath: `page-${p.page}.jpg`, thumbPath: null }));
  return {
    pages: {
      list: async () => [...rows].reverse(),
      uri: async (p: StoredPage) => (missing.includes(p.page) ? null : `file:///vault/an_masks/${p.filePath}`),
    },
  } as unknown as Vault;
}

describe('stored pages with a masked first page', () => {
  const masked = [page(1, [{ x0: 0.1, y0: 0.1, x1: 0.5, y1: 0.3 }]), page(2), page(3)];

  it('saving keeps pages 2 and 3 under their own numbers (page 1 keeps no image on native)', () => {
    const { doc, pages } = buildStoredDocument({ analysis, pages: masked, memberId: 'me', keepPages: true, hideIds: false, now: new Date(), t });
    expect(pages.map((p) => p.page)).toEqual([2, 3]);
    expect(pages.map((p) => p.base64Jpeg)).toEqual(['/9j/PAGE2', '/9j/PAGE3']);
    expect(doc.keepPages).toBe(true);
    expect(doc.pageCount).toBe(3);
  });

  it('web (boxes burned into the display page) keeps all three', () => {
    const { pages } = buildStoredDocument({ analysis, pages: masked, memberId: 'me', keepPages: true, hideIds: false, now: new Date(), t, masksBurnedIn: true });
    expect(pages.map((p) => p.page)).toEqual([1, 2, 3]);
  });

  it('reading back continues past the gap: [gap, page 2, page 3]', async () => {
    const { pages } = buildStoredDocument({ analysis, pages: masked, memberId: 'me', keepPages: true, hideIds: false, now: new Date(), t });
    const slots = await loadStoredPageSlots(vaultWith(pages), 'an_masks');
    expect(slots).toHaveLength(3);
    expect(isPageGap(slots[0])).toBe(true);
    expect(slots[1]).toMatchObject({ id: 'an_masks-p2', uri: 'file:///vault/an_masks/page-2.jpg', mimeType: 'image/jpeg', masks: [] });
    expect(slots[2].uri).toBe('file:///vault/an_masks/page-3.jpg');
  });

  it('a missing file is a gap too; trailing gaps are not padded; bad numbers are ignored', async () => {
    const inputs = [1, 2, 4].map((n) => ({ page: n, base64Jpeg: 'x' }));
    const slots = await loadStoredPageSlots(vaultWith(inputs, [2]), 'an_masks');
    expect(slots.map((p) => (isPageGap(p) ? 'gap' : p.id))).toEqual(['an_masks-p1', 'gap', 'gap', 'an_masks-p4']);
    expect(await loadStoredPageSlots(vaultWith([{ page: 1, base64Jpeg: 'x' }], [1]), 'an_masks')).toEqual([]);
    expect(await loadStoredPageSlots(vaultWith([{ page: 0, base64Jpeg: 'x' }, { page: 9999, base64Jpeg: 'x' }]), 'an_masks')).toEqual([]);
  });
});
