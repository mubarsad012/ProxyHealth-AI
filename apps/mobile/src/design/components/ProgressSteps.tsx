// Honest three-step progress (PRODUCT_SPEC §5.3 loading state, S1b, S6): labelled steps, an
// `aria-live="polite"` announcement of the active step, a bar that mirrors in RTL. With
// reduce-motion on, nothing animates (there is no animation here at all).

import { StyleSheet, View } from 'react-native';

import { Icon } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';

export interface ProgressStepsProps {
  steps: string[];
  /** Index of the step in progress; `steps.length` means all done. */
  active: number;
  /** Announce step changes to screen readers (default true). */
  live?: boolean;
}

export function ProgressSteps({ steps, active, live = true }: ProgressStepsProps) {
  const { colors } = useTheme();
  const dir = useDirection();
  const clamped = Math.max(0, Math.min(active, steps.length));
  const fraction = steps.length ? Math.min(1, (clamped + 0.5) / steps.length) : 0;
  const current = steps[Math.min(clamped, steps.length - 1)] ?? '';
  return (
    <View style={styles.wrap}>
      <View
        role="progressbar"
        accessibilityValue={{ min: 0, max: steps.length, now: clamped, text: current }}
        style={[styles.track, { backgroundColor: colors.divider, flexDirection: dir.row }]}>
        <View style={[styles.fill, { width: `${Math.round(fraction * 100)}%`, backgroundColor: colors.primary }]} />
      </View>
      <View aria-live={live ? 'polite' : 'off'} accessibilityLiveRegion={live ? 'polite' : 'none'}>
        {steps.map((label, i) => {
          const done = i < clamped;
          const now = i === clamped;
          return (
            <View key={label} style={[styles.step, { flexDirection: dir.row }]}>
              <View
                style={[
                  styles.dot,
                  {
                    borderColor: done || now ? colors.primary : colors.border,
                    backgroundColor: done ? colors.primary : 'transparent',
                  },
                ]}>
                {done ? <Icon name="check" size={16} color={colors.onPrimary} /> : null}
              </View>
              <AppText weight={now ? 'bold' : 'regular'} color={done || now ? 'text' : 'textMuted'}>
                {label}
              </AppText>
            </View>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  track: {
    height: 8,
    borderRadius: radius.pill,
    overflow: 'hidden',
  },
  fill: {
    height: 8,
    borderRadius: radius.pill,
  },
  step: {
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.xs,
  },
  dot: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
