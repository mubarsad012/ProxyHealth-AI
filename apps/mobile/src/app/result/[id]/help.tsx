// S11 for one paper (`/result/[id]/help?tags=a,b&focus=<resource_id>`); renders WP6's
// `HelpForDocument` seam inside the standard screen scaffold.

import { type Href, router, useLocalSearchParams } from 'expo-router';

import type { ResourceTag } from '@/api/types';
import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { useAnalysisFor } from '@/features/analysis/ResultScreen';
import { HelpForDocument } from '@/features/help';
import { useT } from '@/i18n/useT';

export default function ResultHelpRoute() {
  const t = useT();
  const params = useLocalSearchParams<{ id: string; tags?: string; focus?: string }>();
  const { analysis, loading } = useAnalysisFor(String(params.id ?? ''));
  const tags = params.tags ? (params.tags.split(',').filter(Boolean) as ResourceTag[]) : null;
  return (
    <Screen back title={t('card.help_preview')}>
      {analysis ? (
        <HelpForDocument analysis={analysis} tags={tags} focus={params.focus ?? null} />
      ) : loading ? null : (
        <EmptyState text={t('notfound.title')} actionLabel={t('btn.go_home')} onAction={() => router.replace('/' as Href)} />
      )}
    </Screen>
  );
}
