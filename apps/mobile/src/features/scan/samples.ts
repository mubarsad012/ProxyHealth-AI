// Sample papers on S5 (`/scan/review?sample=<fixture_id>`, D-29). Pages are the server's fixture
// PNGs (`GET /v1/demo/fixtures/{id}/pages/{n}`); the request sends `pages: []` + `demo_sample_id`.

import type { ApiClient } from '@/api/client';
import { bundledFixture } from '@/api/offline';
import type { CapturedPage } from '@/store/session';

export function samplePages(client: ApiClient, id: string, count?: number): CapturedPage[] {
  const n = Math.max(1, count ?? bundledFixture(id)?.pages ?? 1);
  return Array.from({ length: n }, (_, i) => ({
    id: `sample_${id}_${i + 1}`,
    uri: client.fixturePageUrl(id, i + 1),
    mimeType: 'image/png' as const,
    rotation: 0 as const,
    masks: [],
    source: 'sample' as const,
  }));
}
