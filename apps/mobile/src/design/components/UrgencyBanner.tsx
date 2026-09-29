// Urgency banner (PRODUCT_SPEC §5.5, D-12): icon + word + colour, never colour alone, never CAPS.
// Data comes from `AnalysisResult.urgency` (computed server-side); the client adds the days line
// and the floor note. `{date}` renders LTR-isolated. CTAs appear only when their handler is given.

import { StyleSheet, View } from 'react-native';

import type { Urgency } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { Interpolated } from '@/design/components/Interpolated';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space, urgency as urgencyTokens } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';

export interface UrgencyBannerProps {
  urgency: Urgency;
  onVerify?(): void;
  onRemind?(): void;
}

/** The headline key actually rendered (emergency and past-date rules of §5.5). */
export function urgencyHeadlineKey(u: Urgency): string {
  if (u.level === 'emergency') return 'urgency.emergency.headline';
  if (u.past_date) return 'urgency.critical.date_passed';
  return u.headline_key;
}

/** `urgency.days_until` / `urgency.days_ago` line, or null. */
export function urgencyDaysLine(u: Urgency): { key: string; days: number } | null {
  if (u.days_until === null || u.days_until === undefined) return null;
  if (u.days_until < 0) return { key: 'urgency.days_ago', days: Math.abs(u.days_until) };
  return { key: 'urgency.days_until', days: u.days_until };
}

export function UrgencyBanner({ urgency, onVerify, onRemind }: UrgencyBannerProps) {
  const t = useT();
  const theme = useTheme();
  const dir = useDirection();
  const token = urgencyTokens[urgency.level];
  const color = token.color[theme.name];
  const word = t(token.wordKey);
  const days = urgencyDaysLine(urgency);
  return (
    <View
      role="alert"
      accessibilityLabel={word}
      style={[styles.box, { borderColor: color, backgroundColor: theme.colors.surfaceRaised }]}>
      <View style={[styles.row, { flexDirection: dir.row }]}>
        <Icon name={token.icon} color={color} size={28} />
        <AppText variant="bodyLarge" weight="bold" colorValue={color}>
          {word}
        </AppText>
      </View>
      <Interpolated
        template={t(urgencyHeadlineKey(urgency))}
        vars={urgency.headline_params ?? {}}
        variant="bodyLarge"
      />
      {days ? <AppText color="textMuted">{t(days.key, { days: days.days })}</AppText> : null}
      {urgency.floor_applied ? <AppText color="textMuted">{t('urgency.floor_note')}</AppText> : null}
      {onVerify || onRemind ? (
        <View style={[styles.actions, { flexDirection: dir.row }]}>
          {urgency.past_date && onVerify ? (
            <BigButton label={t('btn.verify_date')} icon="phone" variant="primary" size={56} onPress={onVerify} />
          ) : null}
          {onRemind && !urgency.past_date ? (
            <BigButton label={t('btn.remind_me')} icon="calendar" variant="primary" size={56} onPress={onRemind} />
          ) : null}
          {onVerify && !urgency.past_date ? (
            <BigButton label={t('btn.verify_date')} icon="phone" variant="secondary" size={56} onPress={onVerify} />
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    borderWidth: 3,
    borderRadius: radius.lg,
    padding: space.lg,
    gap: space.sm,
  },
  row: {
    alignItems: 'center',
    gap: space.sm,
  },
  actions: {
    flexWrap: 'wrap',
    gap: space.sm,
    marginTop: space.sm,
  },
});
