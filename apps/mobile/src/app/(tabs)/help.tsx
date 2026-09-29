// S11 Get help tab (PRODUCT_SPEC S11): need tiles, region control, resource list. Query
// `?tags=a,b` preselects tags (e.g. from troubleshoot "Ask a person"); `?focus=<id>` expands one.

import { useLocalSearchParams } from 'expo-router';

import type { ResourceTag } from '@/api/types';
import { HelpTabScreen } from '@/features/help';

export default function HelpTab() {
  const params = useLocalSearchParams<{ tags?: string; focus?: string }>();
  const tags = typeof params.tags === 'string' && params.tags ? (params.tags.split(',') as ResourceTag[]) : null;
  const focus = typeof params.focus === 'string' ? params.focus : null;
  return <HelpTabScreen initialTags={tags} focus={focus} />;
}
