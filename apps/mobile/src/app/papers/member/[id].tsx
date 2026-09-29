// S13 — Member detail (PRODUCT_SPEC S13), route `/papers/member/[id]`.

import { useLocalSearchParams } from 'expo-router';

import { MemberScreen } from '@/features/vault/MemberScreen';

export default function MemberRoute() {
  const { id } = useLocalSearchParams<{ id: string }>();
  return <MemberScreen memberId={typeof id === 'string' ? id : ''} />;
}
