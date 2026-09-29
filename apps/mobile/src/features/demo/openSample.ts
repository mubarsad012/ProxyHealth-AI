// What a sample pick does (PRODUCT_SPEC §12.2): the pages go into the session as display-only
// sample pages with `demoSampleId` set; documents open S5 (`/scan/review?sample=<id>`), the
// screenshot opens S16 (`/troubleshoot?sample=<id>`).

import { type Href, router } from 'expo-router';

import type { DemoFixture } from '@/api/types';
import { type CapturedPage, useSession } from '@/store/session';

export function sampleHref(sample: Pick<DemoFixture, 'id' | 'kind'>): string {
  const id = encodeURIComponent(sample.id);
  return sample.kind === 'screenshot' ? `/troubleshoot?sample=${id}` : `/scan/review?sample=${id}`;
}

export function openSample(sample: DemoFixture, pages: CapturedPage[]): void {
  const session = useSession.getState();
  session.setCurrentAnalysis(null);
  session.setPages(pages);
  session.setDemoSampleId(sample.id);
  router.push(sampleHref(sample) as Href);
}
