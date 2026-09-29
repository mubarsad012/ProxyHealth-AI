// S15 — Quick sheet for a result (`/result/[id]/quicksheet`); renders WP6's `QuickSheetScreen` seam.

import { type Href, router, useLocalSearchParams } from 'expo-router';

import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { useAnalysisFor } from '@/features/analysis/ResultScreen';
import { QuickSheetScreen } from '@/features/quicksheet';
import { useT } from '@/i18n/useT';

export default function QuickSheetRoute() {
  const t = useT();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { analysis, loading, documentId } = useAnalysisFor(String(id ?? ''));
  if (!analysis) {
    return (
      <Screen back>
        {loading ? null : (
          <EmptyState text={t('notfound.title')} actionLabel={t('btn.go_home')} onAction={() => router.replace('/' as Href)} />
        )}
      </Screen>
    );
  }
  return <QuickSheetScreen analysis={analysis} documentId={documentId ?? undefined} />;
}
