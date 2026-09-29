// S18 — Not found / root error boundary (PRODUCT_SPEC S18): friendly copy, "Go home", "Report a
// problem" (counts only). Never a stack trace for users; development builds show a collapsible.

import { type Href, router } from 'expo-router';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '@/api/config';
import { BigButton } from '@/design/components/BigButton';
import { Collapsible } from '@/design/components/Collapsible';
import { buildFeedbackRequest } from '@/design/components/FeedbackRow';
import { Screen } from '@/design/components/Screen';
import { AppText, Heading } from '@/design/components/Text';
import { space } from '@/design/tokens';
import { usePackMeta, useT } from '@/i18n/useT';
import { isProduction } from '@/lib/platform';

export interface NotFoundScreenProps {
  /** Present when rendered as the error boundary. */
  error?: Error;
  retry?(): void;
}

export function NotFoundScreen({ error, retry }: NotFoundScreenProps) {
  const t = useT();
  const api = useApi();
  const meta = usePackMeta();
  const [reported, setReported] = useState(false);
  const report = () => {
    setReported(true);
    api.feedback(buildFeedbackRequest({ surface: 'summary' }, 'unclear', meta.tag)).catch(() => undefined);
  };
  return (
    <Screen testID="not-found-screen">
      <Heading level={1}>{t('notfound.title')}</Heading>
      <AppText>{t('notfound.body')}</AppText>
      <View style={styles.actions}>
        <BigButton
          label={t('btn.go_home')}
          icon="home"
          variant="primary"
          size={72}
          onPress={() => {
            retry?.();
            router.replace('/' as Href);
          }}
        />
        {reported ? (
          <AppText role="status" color="textMuted">
            {t('feedback.thanks')}
          </AppText>
        ) : (
          <BigButton label={t('btn.report_problem')} icon="flag" variant="secondary" size={56} onPress={report} />
        )}
      </View>
      {error && !isProduction ? (
        <Collapsible title={error.name}>
          <AppText variant="caption" align="auto">
            {error.message}
          </AppText>
        </Collapsible>
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  actions: {
    gap: space.md,
  },
});
