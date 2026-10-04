// Data-use tier badge (D-02, PRODUCT_SPEC S2, COMPLIANCE_PRIVACY §4.2): the word is announced, not
// only the colour. `unpaid` and `mixed` share the red "Test build — free AI key" badge; `none`
// (no keys configured) renders like `unknown` (PRODUCT_SPEC §5.3). Phase 3 (free-ai-providers
// §5.2): `local` → `consent.badge.local` ("Test build — AI on our server") and `attested` →
// `consent.badge.attested` ("Test build — outside AI"), both in the warning colour.

import { StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import type { Palette } from '@/design/tokens';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { UiTier } from '@/store/session';

export type BadgeTier = 'paid' | 'unpaid' | 'demo' | 'local' | 'attested' | 'unknown';

/** Collapse the eight UI tiers into the six badges. */
export function badgeTier(tier: UiTier): BadgeTier {
  if (tier === 'paid') return 'paid';
  if (tier === 'unpaid' || tier === 'mixed') return 'unpaid';
  if (tier === 'demo') return 'demo';
  if (tier === 'local') return 'local';
  if (tier === 'attested') return 'attested';
  return 'unknown';
}

export function tierBadgeKey(tier: UiTier): string {
  return `consent.badge.${badgeTier(tier)}`;
}

const LOOK: Record<BadgeTier, { icon: IconName; color: keyof Palette }> = {
  paid: { icon: 'lock', color: 'success' },
  unpaid: { icon: 'alert', color: 'danger' },
  demo: { icon: 'sample', color: 'primary' },
  local: { icon: 'server', color: 'warning' },
  attested: { icon: 'cloud', color: 'warning' },
  unknown: { icon: 'info', color: 'warning' },
};

export function TierBadge({ tier }: { tier: UiTier }) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const b = badgeTier(tier);
  const color = colors[LOOK[b].color];
  const word = t(tierBadgeKey(tier));
  return (
    <View
      testID={`tier-badge-${b}`}
      accessible
      accessibilityRole="text"
      accessibilityLabel={word}
      style={[styles.badge, { borderColor: color, flexDirection: dir.row, alignSelf: dir.alignStart }]}>
      <Icon name={LOOK[b].icon} color={color} size={20} />
      <AppText variant="caption" weight="bold" colorValue={color}>
        {word}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignItems: 'center',
    gap: space.xs,
    paddingHorizontal: space.md,
    paddingVertical: space.xs,
    borderRadius: radius.pill,
    borderWidth: 2,
  },
});
