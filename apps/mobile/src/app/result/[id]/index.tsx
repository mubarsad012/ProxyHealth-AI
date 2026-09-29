// S7 — Result (`/result/[id]`, id = analysis_id). Screen body lives in features/analysis.

import { useLocalSearchParams } from 'expo-router';

import { ResultScreen } from '@/features/analysis/ResultScreen';

export default function ResultRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <ResultScreen id={String(id ?? '')} />;
}
