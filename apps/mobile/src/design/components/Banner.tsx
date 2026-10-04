// Banners (PRODUCT_SPEC §5.3/§5.6, §11.5): demo / unpaid / offline / machine-translation / partial
// pack, and the Phase 3 test-build tiers (free-ai-providers §5.2/§5.3): `local` →
// `banner.local_tier`, `attested` → `banner.attested_tier`. Icon + words; the unpaid and attested
// banners are strong (thick border, bold, `role="alert"`), never colour alone. `TierBanner` picks
// the tier's banner (or none) from the UI tier, so screens need no tier switch of their own.
// `text` overrides the default copy (e.g. `banner.demo_sample` on results instead of
// `banner.sample_mode` on Home).
//
// Pack provenance (COMPLIANCE_PRIVACY §5.2, D-25): the `Screen` scaffold shows the
// machine-translation / partial-pack banner on every screen. A screen that renders the same banner
// itself (S2, the S7 result banners) registers it with the surrounding `PackBannerScope`, and the
// scaffold then leaves its own copy out, so the line never appears twice.

import { createContext, useContext, useEffect } from 'react';
import { StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import type { Palette } from '@/design/tokens';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { UiTier } from '@/store/session';

export type BannerKind =
  | 'demo'
  | 'unpaid'
  | 'local'
  | 'attested'
  | 'offline'
  | 'machine_translation'
  | 'partial_pack';

export const BANNER_KEYS: Record<BannerKind, string> = {
  demo: 'banner.sample_mode',
  unpaid: 'banner.unpaid_tier',
  local: 'banner.local_tier',
  attested: 'banner.attested_tier',
  offline: 'banner.offline',
  machine_translation: 'banner.machine_translated',
  partial_pack: 'banner.partial_pack',
};

const LOOK: Record<BannerKind, { icon: IconName; color: keyof Palette }> = {
  demo: { icon: 'sample', color: 'primary' },
  unpaid: { icon: 'alert', color: 'danger' },
  local: { icon: 'server', color: 'warning' },
  attested: { icon: 'alert', color: 'warning' },
  offline: { icon: 'offline', color: 'textMuted' },
  machine_translation: { icon: 'globe', color: 'warning' },
  partial_pack: { icon: 'globe', color: 'warning' },
};

export type PackBannerKind = 'machine_translation' | 'partial_pack';

export interface PackBannerScopeValue {
  /** A screen-rendered provenance banner mounted; returns its unregister function. */
  register(kind: PackBannerKind): () => void;
}

/** Provided by `Screen`; `null` (e.g. around the scaffold's own banners) means "do not register". */
export const PackBannerScope = createContext<PackBannerScopeValue | null>(null);

export interface BannerProps {
  kind: BannerKind;
  text?: string;
}

export function Banner({ kind, text }: BannerProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const scope = useContext(PackBannerScope);
  const look = LOOK[kind];
  const color = colors[look.color];
  const copy = text ?? t(BANNER_KEYS[kind]);
  const provenance: PackBannerKind | null =
    (kind === 'machine_translation' || kind === 'partial_pack') && copy === t(BANNER_KEYS[kind]) ? kind : null;
  const strong = STRONG.has(kind);
  useEffect(() => {
    if (!scope || !provenance) return undefined;
    return scope.register(provenance);
  }, [scope, provenance]);
  return (
    <View
      testID={`banner-${kind}`}
      role={strong ? 'alert' : 'status'}
      accessibilityLabel={copy}
      style={[
        styles.banner,
        { flexDirection: dir.row, borderColor: color, backgroundColor: colors.surface },
        strong ? styles.strong : null,
      ]}>
      <Icon name={look.icon} color={color} />
      <View style={styles.text}>
        <AppText variant="caption" weight={strong ? 'bold' : 'regular'}>
          {copy}
        </AppText>
      </View>
    </View>
  );
}

/** Data-use tier → its banner (free-ai-providers §5.2): unpaid/mixed → `unpaid`, `local`, `attested`;
 *  paid, demo (Home shows its own sample-mode banner), none and unknown → none. */
export function tierBannerKind(tier: UiTier): 'unpaid' | 'local' | 'attested' | null {
  if (tier === 'unpaid' || tier === 'mixed') return 'unpaid';
  if (tier === 'local') return 'local';
  if (tier === 'attested') return 'attested';
  return null;
}

/** The tier's test-build banner, or nothing. Replaces `{unpaid ? <Banner kind="unpaid" /> : null}`. */
export function TierBanner({ tier }: { tier: UiTier }) {
  const kind = tierBannerKind(tier);
  return kind ? <Banner kind={kind} /> : null;
}

const STRONG: ReadonlySet<BannerKind> = new Set<BannerKind>(['unpaid', 'attested']);

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
