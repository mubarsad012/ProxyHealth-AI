// S14 — Reminders (PRODUCT_SPEC S14), route `/reminders?doc=<analysis_id>`.

import { useLocalSearchParams } from 'expo-router';

import { RemindersScreen } from '@/features/reminders/RemindersScreen';

export default function RemindersRoute() {
  const { doc } = useLocalSearchParams<{ doc?: string }>();
  return <RemindersScreen focusDocumentId={typeof doc === 'string' ? doc : null} />;
}
