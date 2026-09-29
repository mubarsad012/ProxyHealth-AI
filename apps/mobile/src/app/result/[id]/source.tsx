// S8 — Original and translation (`/result/[id]/source?block=<span_id>&page=<n>`).

import { type Href, router, useLocalSearchParams } from 'expo-router';

import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { useAnalysisFor } from '@/features/analysis/ResultScreen';
import { SourceScreen } from '@/features/analysis/SourceScreen';
import { useT } from '@/i18n/useT';

export default function SourceRoute() {
  const t = useT();
  const params = useLocalSearchParams<{ id: string; block?: string; page?: string }>();
  const { analysis, pages, loading, documentId } = useAnalysisFor(String(params.id ?? ''));
  if (!analysis) {
    return (
      <Screen back>
        {loading ? null : (
          <EmptyState text={t('notfound.title')} actionLabel={t('btn.go_home')} onAction={() => router.replace('/' as Href)} />
        )}
      </Screen>
    );
  }
  return (
    <SourceScreen
      analysis={analysis}
      pages={pages}
      block={params.block ?? null}
      page={params.page ?? null}
      imagesKept={!documentId || pages.length > 0 || Boolean(analysis.page_thumbnails?.length)}
    />
  );
}
