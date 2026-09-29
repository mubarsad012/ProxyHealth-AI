// S6 — Reading your paper (`/scan/reading`). Honest three-step progress, Cancel aborts the request
// (nothing to clean up server-side), and every failure has a next step (D-07, PRODUCT_SPEC §5.4).

import { Image } from 'expo-image';
import { type Href, router } from 'expo-router';
import { useEffect, useRef } from 'react';
import { Linking, StyleSheet, View } from 'react-native';

import type { ApiError } from '@/api/errors';
import { BigButton } from '@/design/components/BigButton';
import { ProgressSteps } from '@/design/components/ProgressSteps';
import { Screen } from '@/design/components/Screen';
import { ErrorState } from '@/design/components/States';
import { AppText } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { useAnalyze } from '@/features/analysis/useAnalyze';
import { useI18n } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { newId } from '@/lib/ids';
import { useSession } from '@/store/session';

const BACK_TO_PAGES: ReadonlySet<string> = new Set([
  'too_many_pages',
  'pdf_too_long',
  'payload_too_large',
  'unsupported_media_type',
  'invalid_request',
  'model_output_invalid',
]);

function backToReview() {
  if (router.canGoBack()) router.back();
  else router.replace('/scan/review' as Href);
}

function saveForLater() {
  const s = useSession.getState();
  if (!s.pages.length || s.demoSampleId) return;
  s.enqueueOfflineScan({ id: newId(), pages: s.pages, targetLanguage: useI18n.getState().tag, memberId: null, queuedAt: new Date().toISOString() });
}

export function ReadingScreen() {
  const t = useT();
  const run = useAnalyze();
  const started = useRef(false);
  const pages = useSession((s) => s.pages);
  const isSample = useSession((s) => Boolean(s.demoSampleId));
  const { start, status, result } = run;

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    start();
  }, [start]);

  useEffect(() => {
    if (status === 'done' && result) router.replace(`/result/${encodeURIComponent(result.analysis_id)}` as Href);
  }, [status, result]);

  const cancel = () => {
    run.cancel();
    backToReview();
  };

  if (status === 'error' && run.error) {
    return (
      <Screen back onBack={cancel} testID="reading-screen">
        <ReadingError error={run.error} onRetry={start} sample={isSample} />
      </Screen>
    );
  }

  if (status === 'unreadable') {
    const first = pages[0];
    return (
      <Screen back onBack={cancel} testID="reading-screen">
        <View role="alert" style={styles.stack}>
          <AppText variant="bodyLarge" weight="bold">
            {t('state.unreadable')}
          </AppText>
          {first && first.mimeType !== 'application/pdf' ? (
            <Image source={{ uri: first.uri }} contentFit="contain" style={styles.page} accessibilityLabel={t('state.unreadable')} />
          ) : null}
          <BigButton label={t('btn.retake')} icon="camera" variant="primary" size={72} onPress={backToReview} />
        </View>
      </Screen>
    );
  }

  const steps = [t('reading.step1'), t('reading.step2'), t('reading.step3')];
  return (
    <Screen testID="reading-screen" footer={<BigButton label={t('btn.cancel')} icon="close" variant="secondary" size={56} onPress={cancel} />}>
      <ProgressSteps steps={steps} active={run.step} live />
      <AppText>{t('reading.trust_line')}</AppText>
      <AppText color="textMuted">{t('reading.eta')}</AppText>
      {run.tipKey ? (
        <AppText role="status" color="textMuted">
          {t(run.tipKey)}
        </AppText>
      ) : null}
    </Screen>
  );
}

function ReadingError({ error, onRetry, sample }: { error: ApiError; onRetry(): void; sample: boolean }) {
  const t = useT();
  if (error.isConsentRequired()) {
    return (
      <View role="alert" style={styles.stack}>
        <AppText>{t('err.consent_required')}</AppText>
        <BigButton label={t('btn.continue')} variant="primary" size={72} onPress={() => router.push('/onboarding/consent' as Href)} />
      </View>
    );
  }
  if (error.isBlocked()) {
    return (
      <View role="alert" style={styles.stack}>
        <AppText>{t('err.content_blocked')}</AppText>
        {sample ? null : <BigButton label={t('btn.hide_and_retry')} icon="lock" variant="primary" size={72} onPress={backToReview} />}
        <BigButton label={t('btn.get_help')} icon="help" variant="secondary" size={56} onPress={() => router.push('/help' as Href)} />
      </View>
    );
  }
  const offlineLike = error.isOffline() || error.isQuotaExhausted() || error.code === 'upstream_unavailable';
  return (
    <View style={styles.stack}>
      <ErrorState
        error={error}
        onRetry={onRetry}
        onSaveLater={
          offlineLike && !sample
            ? () => {
                saveForLater();
                router.replace('/' as Href);
              }
            : undefined
        }
        onCall211={() => void Linking.openURL('tel:211').catch(() => undefined)}
        onTrySample={() => router.replace('/?sample=1' as Href)}
      />
      {BACK_TO_PAGES.has(error.code) ? (
        <BigButton label={t('btn.back')} icon="arrow-back" variant="secondary" size={56} onPress={backToReview} />
      ) : null}
      {error.isUnpaidBlocked() || error.code === 'not_found' || error.code === 'unauthorized' ? (
        <BigButton label={t('btn.go_home')} icon="home" variant="secondary" size={56} onPress={() => router.replace('/' as Href)} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: space.lg,
  },
  page: {
    width: '100%',
    aspectRatio: 0.77,
  },
});
