// "Was this clear?" row (PRODUCT_SPEC §11, D-31): thumbs up counts `clear`; thumbs down opens the
// fixed kinds; nothing but enums is sent (`POST /v1/feedback` via `client.feedback`). Never any
// text of the paper, never free text.

import Constants from 'expo-constants';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { useApi } from '@/api/config';
import type { DocumentCategory, DocumentType, FeedbackKind, FeedbackRequest, FeedbackSurface } from '@/api/types';
import { Icon, type IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import { platformName } from '@/lib/platform';

export interface FeedbackRowProps {
  surface: FeedbackSurface;
  cardId?: string | null;
  documentType?: DocumentType | null;
  documentCategory?: DocumentCategory | null;
  resourceId?: string | null;
  modelId?: string | null;
  /** Start with the kinds list open (low-confidence translations, PRODUCT_SPEC §5.3). */
  expanded?: boolean;
}

export const NEGATIVE_KINDS: readonly FeedbackKind[] = [
  'unclear',
  'wrong_word',
  'wrong_fact',
  'offensive',
  'scam_missed',
  'resource_problem',
];

export function appVersion(): string {
  return Constants.expoConfig?.version ?? '1.0.0';
}

/** The counts-only request body (exported for tests). */
export function buildFeedbackRequest(props: FeedbackRowProps, kind: FeedbackKind, languageTag: string): FeedbackRequest {
  return {
    app_version: appVersion(),
    kind,
    surface: props.surface,
    language_tag: languageTag,
    platform: platformName(),
    card_id: props.cardId ?? null,
    document_type: props.documentType ?? null,
    document_category: props.documentCategory ?? null,
    resource_id: props.resourceId ?? null,
    model_id: props.modelId ?? null,
  };
}

export function FeedbackRow(props: FeedbackRowProps) {
  const t = useT();
  const api = useApi();
  const meta = usePackMeta();
  const { colors } = useTheme();
  const dir = useDirection();
  const [open, setOpen] = useState(Boolean(props.expanded));
  const [sent, setSent] = useState(false);

  const send = (kind: FeedbackKind) => {
    setSent(true);
    setOpen(false);
    api.feedback(buildFeedbackRequest(props, kind, meta.tag)).catch(() => undefined);
  };

  if (sent) {
    return (
      <View role="status" style={styles.wrap}>
        <AppText variant="caption" color="textMuted">
          {t('feedback.thanks')}
        </AppText>
      </View>
    );
  }

  const thumb = (icon: IconName, label: string, onPress: () => void) => (
    <Pressable
      role="button"
      accessibilityLabel={label}
      hitSlop={size.hitSlop}
      onPress={onPress}
      style={[styles.thumb, { borderColor: colors.border }]}>
      <Icon name={icon} color={colors.primary} />
    </Pressable>
  );

  return (
    <View style={styles.wrap}>
      <View style={[styles.row, { flexDirection: dir.row }]}>
        <View style={styles.question}>
          <AppText>{t('feedback.question')}</AppText>
        </View>
        {thumb('thumb-up', t('btn.yes'), () => send('clear'))}
        {thumb('thumb-down', t('btn.no'), () => setOpen((o) => !o))}
      </View>
      {open ? (
        <View style={styles.kinds}>
          <AppText weight="bold">{t('feedback.what_wrong')}</AppText>
          {NEGATIVE_KINDS.map((k) => (
            <Pressable
              key={k}
              role="button"
              accessibilityLabel={t(`feedback.kind.${k}`)}
              hitSlop={size.hitSlop}
              onPress={() => send(k)}
              style={[styles.kind, { borderColor: colors.border }]}>
              <AppText>{t(`feedback.kind.${k}`)}</AppText>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.sm,
    paddingVertical: space.sm,
  },
  row: {
    alignItems: 'center',
    gap: space.sm,
  },
  question: {
    flex: 1,
  },
  thumb: {
    width: size.minTouch,
    height: size.minTouch,
    borderWidth: 1,
    borderRadius: size.minTouch / 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  kinds: {
    gap: space.sm,
  },
  kind: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    paddingHorizontal: space.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
});
