// S9 — Ask about this paper (`/result/[id]/chat`, `?q=<prompt tapped on S7>`).

import { type Href, router, useLocalSearchParams } from 'expo-router';

import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { useAnalysisFor } from '@/features/analysis/ResultScreen';
import { ChatScreen } from '@/features/chat';
import { useT } from '@/i18n/useT';

export default function ChatRoute() {
  const t = useT();
  const { id, q } = useLocalSearchParams<{ id: string; q?: string }>();
  const { analysis, loading } = useAnalysisFor(String(id ?? ''));
  if (!analysis) {
    return (
      <Screen back>
        {loading ? null : (
          <EmptyState text={t('notfound.title')} actionLabel={t('btn.go_home')} onAction={() => router.replace('/' as Href)} />
        )}
      </Screen>
    );
  }
  return <ChatScreen analysis={analysis} initialQuestion={typeof q === 'string' ? q : null} />;
}
