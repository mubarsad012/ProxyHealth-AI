// S1b — "Adapting system environment to your language..." (D-25, PRODUCT_SPEC S1b,
// COMPLIANCE_PRIVACY §4.1). Honest progress: three labelled steps advancing on timers (0 s / 3 s /
// 15 s) until the pack arrives; English stays active meanwhile; cancel returns to S1. Only the
// typed language name is sent — no consent needed.

import { type Href, router } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { type ApiError, toApiError } from '@/api/errors';
import { BigButton } from '@/design/components/BigButton';
import { ProgressSteps } from '@/design/components/ProgressSteps';
import { Screen } from '@/design/components/Screen';
import { ErrorState } from '@/design/components/States';
import { AppText, Heading } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { switchLanguage } from '@/i18n/language';
import { LANGUAGES } from '@/i18n/languages';
import { useT } from '@/i18n/useT';
import { isOnline } from '@/lib/network';

import { useConsentDecision } from './consentState';
import { afterLanguageHref, leaveLanguageFlow } from './LanguageScreen';

export const STEP_TIMERS_MS = [0, 3000, 15000] as const;

export interface AdaptingScreenProps {
  query: string;
  from?: 'onboarding' | 'settings';
  /** Moves inside the flow (cancel → S1). */
  navigate?(href: Href): void;
  /** Leaves the flow (to S17, S2 or the tabs); defaults to `leaveLanguageFlow`. */
  finish?(href: Href): void;
}

export function AdaptingScreen({
  query,
  from = 'onboarding',
  navigate = (h) => router.replace(h),
  finish = (h) => leaveLanguageFlow(from, h),
}: AdaptingScreenProps) {
  const t = useT();
  const decision = useConsentDecision((s) => s.decision);
  const [step, setStep] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [offline, setOffline] = useState(false);
  const [done, setDone] = useState<{ partial: boolean; mt: boolean; restart: boolean; name: string } | null>(null);
  const controller = useRef<AbortController | null>(null);

  /** Starts one attempt. Every state update happens in timer callbacks or after an await. */
  const load = useCallback(
    async (c: AbortController) => {
      controller.current = c;
      const timers = STEP_TIMERS_MS.slice(1).map((ms, i) => setTimeout(() => !c.signal.aborted && setStep(i + 1), ms));
      try {
        if (!(await isOnline())) {
          if (!c.signal.aborted) setOffline(true);
          return;
        }
        const { pack, restartPending } = await switchLanguage(query, { signal: c.signal });
        if (c.signal.aborted) return;
        setStep(3);
        setDone({
          partial: pack.fallback_keys.length > 0,
          mt: pack.machine_translated,
          restart: restartPending,
          name: pack.name_native,
        });
      } catch (e) {
        if (!c.signal.aborted) setError(toApiError(e));
      } finally {
        timers.forEach(clearTimeout);
      }
    },
    [query],
  );

  useEffect(() => {
    const c = new AbortController();
    // Started from a timer callback so no state update runs synchronously inside the effect.
    const id = setTimeout(() => void load(c), 0);
    return () => {
      clearTimeout(id);
      c.abort();
    };
  }, [load]);

  const retry = () => {
    setError(null);
    setOffline(false);
    setStep(0);
    void load(new AbortController());
  };

  const cancel = () => {
    controller.current?.abort();
    navigate(`/onboarding/language${from === 'settings' ? '?from=settings' : ''}` as Href);
  };
  const next = () => finish(afterLanguageHref(from, decision));

  const steps = [t('langpack.step_find'), t('langpack.step_translate'), t('langpack.step_check')];

  return (
    <Screen testID="adapting-screen">
      <Heading level={1}>{t('langpack.adapting')}</Heading>
      <AppText variant="bodyLarge" weight="bold" align="auto">
        {done?.name ?? LANGUAGES[query]?.name_native ?? query}
      </AppText>
      {error ? (
        <View style={styles.block}>
          <ErrorState error={error} onRetry={error.code === 'language_unresolved' ? undefined : retry} />
          <BigButton label={t('btn.choose_bundled')} variant="secondary" size={56} onPress={cancel} />
        </View>
      ) : offline ? (
        <View role="alert" style={styles.block}>
          <AppText>{t('state.lang_needs_internet')}</AppText>
          <BigButton label={t('btn.choose_bundled')} variant="primary" size={56} onPress={cancel} />
        </View>
      ) : done ? (
        <View style={styles.block}>
          <ProgressSteps steps={steps} active={3} />
          {done.partial ? <AppText>{t('banner.partial_pack')}</AppText> : null}
          {done.mt ? <AppText>{t('banner.machine_translated')}</AppText> : null}
          {done.restart ? <AppText weight="bold">{t('direction.restart_prompt')}</AppText> : null}
          <BigButton testID="adapting-continue" label={t('btn.continue')} variant="primary" size={72} onPress={next} />
        </View>
      ) : (
        <View style={styles.block}>
          <ProgressSteps steps={steps} active={step} />
          <AppText color="textMuted">{t('langpack.about_20s')}</AppText>
          <AppText color="textMuted">{t('langpack.english_meanwhile')}</AppText>
          <BigButton label={t('btn.cancel')} variant="secondary" size={56} onPress={cancel} />
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  block: {
    gap: space.lg,
  },
});
