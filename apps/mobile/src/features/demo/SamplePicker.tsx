// Sample picker (PRODUCT_SPEC §12.2; a bottom sheet — no route). `SamplePicker` is the list (the
// §4.2 seam); `SamplePickerSheet` wraps it in the WP6 sheet for Home, errors and Settings.
// Rows: thumbnail (server PNG, or the bundled PNG offline — both watermarked SAMPLE), localized
// title (fallback `title_en`), page count, and "A screenshot of a website" for the screenshot,
// which the caller routes to S16 instead of S5.

import { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, StyleSheet, View } from 'react-native';

import { useApi } from '@/api/config';
import type { FixtureListing } from '@/api/offline';
import type { DemoFixture } from '@/api/types';
import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { Sheet } from '@/features/vault/Sheet';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { loadSamples, orderSamples, samplePages, sampleThumbnail, sampleTitle } from './samples';

export interface SamplePickerProps {
  onPick(sample: DemoFixture, pages: CapturedPage[]): void;
}

export function SamplePicker({ onPick }: SamplePickerProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const client = useApi();
  const [listing, setListing] = useState<FixtureListing | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadSamples(client)
      .then((l) => {
        if (!cancelled) setListing(l);
      })
      .catch(() => {
        // `listFixturesWithFallback` already falls back to the bundled manifest; never spin forever.
        if (!cancelled) setListing({ fixtures: [], source: 'bundled' });
      });
    return () => {
      cancelled = true;
    };
  }, [client]);

  if (!listing) {
    return (
      <View style={styles.loading} role="progressbar" accessibilityLabel={t('home.tile_sample')}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }
  return (
    <View style={styles.list} testID="sample-picker">
      <AppText color="textMuted">{t('demo.explainer')}</AppText>
      {orderSamples(listing.fixtures).map((f) => {
        const title = sampleTitle(f, t);
        const thumb = sampleThumbnail(client, f, listing.source);
        const caption = f.kind === 'screenshot' ? t('demo.kind_screenshot') : t('demo.pages', { n: f.pages });
        return (
          <Pressable
            key={f.id}
            testID={`sample-${f.id}`}
            role="button"
            accessibilityLabel={`${title}. ${caption}`}
            hitSlop={size.hitSlop / 2}
            onPress={() => onPick(f, samplePages(client, f, listing.source))}
            style={({ pressed }) => [
              styles.row,
              {
                flexDirection: dir.row,
                borderColor: colors.border,
                backgroundColor: pressed ? colors.secondary : colors.surface,
              },
            ]}>
            {thumb ? (
              <Image source={thumb} style={[styles.thumb, { borderColor: colors.divider }]} resizeMode="cover" />
            ) : (
              <View style={[styles.thumb, styles.center, { borderColor: colors.divider }]}>
                <Icon name={f.kind === 'screenshot' ? 'image' : 'papers'} color={colors.textMuted} />
              </View>
            )}
            <View style={styles.flex}>
              <AppText weight="bold">{title}</AppText>
              <AppText variant="caption" color="textMuted">
                {caption}
              </AppText>
            </View>
            <Icon name="chevron-right" color={colors.textMuted} mirror />
          </Pressable>
        );
      })}
    </View>
  );
}

export interface SamplePickerSheetProps extends SamplePickerProps {
  visible: boolean;
  onClose(): void;
}

export function SamplePickerSheet({ visible, onClose, onPick }: SamplePickerSheetProps) {
  const t = useT();
  return (
    <Sheet visible={visible} title={t('home.tile_sample')} onClose={onClose} testID="sample-picker-sheet">
      {visible ? <SamplePicker onPick={onPick} /> : null}
    </Sheet>
  );
}

const styles = StyleSheet.create({
  loading: {
    minHeight: 120,
    alignItems: 'center',
    justifyContent: 'center',
  },
  list: {
    gap: space.sm,
  },
  row: {
    minHeight: size.button,
    alignItems: 'center',
    gap: space.md,
    padding: space.sm,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  thumb: {
    width: 56,
    height: 72,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  flex: {
    flex: 1,
    gap: space.xxs,
  },
});
