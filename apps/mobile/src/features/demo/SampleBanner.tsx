// The sample-paper banner (`banner.demo_sample`, PRODUCT_SPEC §12.2; the copy lives in en.json and
// is not quoted here, so this comment cannot go stale when the reviewed sentence changes).
// With no props it shows while the current scan is a sample (`session.demoSampleId`) or the
// current result came from one (`model_meta.demo`); pass `analysis` for results read from the
// vault, or `force` on screens that are always about a sample.

import type { AnalysisResult } from '@/api/types';
import { Banner } from '@/design/components/Banner';
import { useT } from '@/i18n/useT';
import { useSession } from '@/store/session';

export interface SampleBannerProps {
  analysis?: AnalysisResult | null;
  force?: boolean;
}

export function SampleBanner(props: SampleBannerProps = {}) {
  const t = useT();
  const demoSampleId = useSession((s) => s.demoSampleId);
  const currentDemo = useSession((s) => Boolean(s.currentAnalysis?.model_meta?.demo));
  const fromProp = props.analysis !== undefined ? Boolean(props.analysis?.model_meta?.demo) : null;
  const show = props.force === true || (fromProp ?? (demoSampleId !== null || currentDemo));
  if (!show) return null;
  return <Banner kind="demo" text={t('banner.demo_sample')} />;
}
