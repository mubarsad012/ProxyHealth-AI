// "Back to me" — exits clerk mode only after a 1.5 s hold (PRODUCT_SPEC §8.3/§8.6). Release early
// cancels. Alternatives: the accessibility "activate" action starts the same timer with an
// announced countdown; on web, holding Space or Enter for 1.5 s works too.

import { useCallback, useEffect, useRef, useState } from 'react';
import { AccessibilityInfo, Platform, Pressable, StyleSheet, View } from 'react-native';

import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useT } from '@/i18n/useT';

import { CLERK_HOLD_MS } from './clerkModel';

export interface LongPressExitProps {
  onExit(): void;
  holdMs?: number;
}

export function LongPressExit({ onExit, holdMs = CLERK_HOLD_MS }: LongPressExitProps) {
  const t = useT();
  const { colors } = useTheme();
  const [progress, setProgress] = useState(0);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAt = useRef(0);
  const exitRef = useRef(onExit);
  useEffect(() => {
    exitRef.current = onExit;
  }, [onExit]);

  const cancel = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    setProgress(0);
  }, []);

  const begin = useCallback(
    (announce: boolean) => {
      if (timer.current) return;
      startedAt.current = Date.now();
      let lastSecond = -1;
      timer.current = setInterval(() => {
        const elapsed = Date.now() - startedAt.current;
        const p = Math.min(1, elapsed / holdMs);
        setProgress(p);
        if (announce) {
          const left = Math.ceil((holdMs - elapsed) / 1000);
          if (left !== lastSecond && left > 0) {
            lastSecond = left;
            try {
              AccessibilityInfo.announceForAccessibility(String(left));
            } catch {
              // best-effort
            }
          }
        }
        if (p >= 1) {
          if (timer.current) clearInterval(timer.current);
          timer.current = null;
          setProgress(0);
          exitRef.current();
        }
      }, 50);
    },
    [holdMs],
  );

  useEffect(() => cancel, [cancel]);

  // Web keyboard alternative: hold Space / Enter.
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const down = (e: KeyboardEvent) => {
      if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) begin(false);
    };
    const up = (e: KeyboardEvent) => {
      if (e.key === ' ' || e.key === 'Enter') cancel();
    };
    document.addEventListener('keydown', down);
    document.addEventListener('keyup', up);
    return () => {
      document.removeEventListener('keydown', down);
      document.removeEventListener('keyup', up);
    };
  }, [begin, cancel]);

  return (
    <Pressable
      testID="clerk-exit"
      role="button"
      accessibilityLabel={t('clerk.back_to_me')}
      accessibilityActions={[{ name: 'activate', label: t('clerk.back_to_me') }]}
      onAccessibilityAction={(e) => {
        if (e.nativeEvent.actionName === 'activate') begin(true);
      }}
      onPressIn={() => begin(false)}
      onPressOut={cancel}
      hitSlop={size.hitSlop}
      style={[styles.button, { borderColor: colors.text, backgroundColor: colors.surfaceRaised }]}>
      <View
        pointerEvents="none"
        style={[styles.fill, { width: `${Math.round(progress * 100)}%`, backgroundColor: colors.secondary }]}
      />
      <AppText variant="bodyLarge" weight="bold" align="center">
        {t('clerk.back_to_me')}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: size.primaryCta,
    justifyContent: 'center',
    borderWidth: 3,
    borderRadius: radius.md,
    paddingHorizontal: space.xl,
    overflow: 'hidden',
  },
  fill: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
  },
});
