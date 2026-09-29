// S10 — Show the clerk (`/result/[id]/clerk`; `id = generic` → the no-analysis card, §8.4).

import { useLocalSearchParams } from 'expo-router';

import { useAnalysisFor } from '@/features/analysis/ResultScreen';
import { ClerkScreen } from '@/features/clerk';

export default function ClerkRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const key = String(id ?? 'generic');
  const { analysis } = useAnalysisFor(key === 'generic' ? '' : key);
  return <ClerkScreen analysis={key === 'generic' ? null : analysis} />;
}
