// Feedback (D-31, API_CONTRACT §3.12; ARCHITECTURE §3 features/feedback). Counts only: the body
// is built by WP4's `buildFeedbackRequest` from enums and ids — never text, quotes or document
// content. This module adds a once-per-session guard so a double tap cannot double count, and a
// helper for WP5 surfaces that post outside a `FeedbackRow` (e.g. "Report a problem").

import type { ApiClient } from '@/api/client';
import type { FeedbackKind, FeedbackResponse } from '@/api/types';
import { buildFeedbackRequest, type FeedbackRowProps } from '@/design/components/FeedbackRow';

const sent = new Set<string>();

export function feedbackKey(props: FeedbackRowProps, kind: FeedbackKind): string {
  return [props.surface, props.cardId ?? '', props.documentType ?? '', props.resourceId ?? '', kind].join('|');
}

/** Post one counts-only feedback event; repeated identical events in a session are dropped. */
export async function sendFeedbackOnce(
  client: Pick<ApiClient, 'feedback'>,
  props: FeedbackRowProps,
  kind: FeedbackKind,
  languageTag: string,
): Promise<FeedbackResponse | null> {
  const key = feedbackKey(props, kind);
  if (sent.has(key)) return null;
  sent.add(key);
  try {
    return await client.feedback(buildFeedbackRequest(props, kind, languageTag));
  } catch {
    sent.delete(key);
    return null;
  }
}

export function resetFeedbackForTests(): void {
  sent.clear();
}
