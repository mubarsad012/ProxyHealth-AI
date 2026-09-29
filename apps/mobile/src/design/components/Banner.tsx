// Banners (PRODUCT_SPEC §5.3/§5.6, §11.5): demo / unpaid / offline / machine-translation / partial
// pack. Icon + words; the unpaid banner is red with an icon and a word, never colour alone.
// `text` overrides the default copy (e.g. `banner.demo_sample` on results instead of
// `banner.sample_mode` on Home).

import { StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import type { Palette } from '@/design/tokens';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

export type BannerKind = 'demo' | 'unpaid' | 'offline' | 'machine_translation' | 'partial_pack';

export const BANNER_KEYS: Record<BannerKind, string> = {
  demo: 'banner.sample_mode',
  unpaid: 'banner.unpaid_tier',
  offline: 'banner.offline',
  machine_translation: 'banner.machine_translated',
  partial_pack: 'banner.partial_pack',
};

const LOOK: Record<BannerKind, { icon: IconName; color: keyof Palette }> = {
  demo: { icon: 'sample', color: 'primary' },
  unpaid: { icon: 'alert', color: 'danger' },
  offline: { icon: 'offline', color: 'textMuted' },
  machine_translation: { icon: 'globe', color: 'warning' },
  partial_pack: { icon: 'globe', color: 'warning' },
};

export interface BannerProps {
  kind: BannerKind;
  text?: string;
}

export function Banner({ kind, text }: BannerProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const look = LOOK[kind];
  const color = colors[look.color];
  const copy = text ?? t(BANNER_KEYS[kind]);
  return (
    <View
      testID={`banner-${kind}`}
      role={kind === 'unpaid' ? 'alert' : 'status'}
      accessibilityLabel={copy}
      style={[
        styles.banner,
        { flexDirection: dir.row, borderColor: color, backgroundColor: colors.surface },
        kind === 'unpaid' ? styles.strong : null,
      ]}>
      <Icon name={look.icon} color={color} />
      <View style={styles.text}>
        <AppText variant="caption" weight={kind === 'unpaid' ? 'bold' : 'regular'}>
          {copy}
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    alignItems: 'center',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  strong: {
    borderWidth: 3,
  },
  text: {
    flex: 1,
  },
});
