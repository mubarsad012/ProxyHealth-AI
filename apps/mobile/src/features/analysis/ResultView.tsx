// S7 result body in the FIXED order of PRODUCT_SPEC S7: emergency card (first when triggered) →
// scam card → warning chips → urgency banner → disclaimer header → banners → Card 1 → Card 2 →
// unverified section → Card 3 → details → glossary → questions → red flags → help preview →
// ask → footer (AI-generated + verify-with-sender + "Was this clear?").

import { Pressable, StyleSheet, View } from 'react-native';

import type { AnalysisResult } from '@/api/types';
import { Banner, type BannerKind } from '@/design/components/Banner';
import { BigButton } from '@/design/components/BigButton';
import { FeedbackRow } from '@/design/components/FeedbackRow';
import { AppText } from '@/design/components/Text';
import { UrgencyBanner } from '@/design/components/UrgencyBanner';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { CHAT_UNAVAILABLE_KEY } from '@/features/chat/refusalTemplates';
import { EmergencyCard, useEmergencyTrigger } from '@/features/emergency';
import { SpeakRow } from '@/features/speech/SpeakRow';
import { useDirection } from '@/i18n/direction';
import { useBidiText, usePackMeta, useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { canRemind, DemandsCard } from './cards/DemandsCard';
import { DetailsSection } from './cards/DetailsSection';
import { HelpPreview } from './cards/HelpPreview';
import { GlossaryCard, QuestionsCard } from './cards/InfoCards';
import { PlanCard } from './cards/PlanCard';
import { RedFlagsCard, ScamCard, WarningChips } from './cards/SafetyCards';
import type { ResultHandlers } from './cards/shared';
import { SummaryCard } from './cards/SummaryCard';
import { disclaimerKey, footerKeys, resultBanners, sampleAsOfNoteKey, type BannerSpec } from './disclaimers';
import { UnverifiedSection } from './unverifiedSection';
import { useLocalizedUrgency } from './estimatedDate';
import { drivingDemand, firstPrintedPhone } from './urgencyCopy';

export interface ResultViewHandlers extends ResultHandlers {
  onEmergencyMoreHelp?(): void;
  onSeeAllHelp?(): void;
  onSetRegion?(): void;
  /** Urgency `verify_resource_id` → S11 `?focus=<id>`. */
  onVerifyResource?(resourceId: string): void;
  onReportProblem?(): void;
}

export interface ResultViewProps {
  analysis: AnalysisResult;
  pages: readonly CapturedPage[];
  handlers: ResultViewHandlers;
  /** Offline: "Ask about this paper" is disabled with `state.offline_disabled`. */
  offline?: boolean;
  /** `/v1/config` `features.chat=false` (unpaid / mixed tier): the ask row explains instead. */
  chatUnavailable?: boolean;
}

const TONE_KIND: Record<BannerSpec['tone'], BannerKind> = {
  danger: 'unpaid',
  warning: 'machine_translation',
  info: 'demo',
};

/** S7 item 16: the first two `questions_to_ask` offered as one-tap prompts for S9. */
export function askPrompts(a: Pick<AnalysisResult, 'questions_to_ask'>): string[] {
  return a.questions_to_ask.map((q) => q.trim()).filter(Boolean).slice(0, 2);
}

export function ResultView({ analysis, pages, handlers, offline, chatUnavailable }: ResultViewProps) {
  const t = useT();
  const bt = useBidiText();
  const meta = usePackMeta();
  const dir = useDirection();
  const { colors } = useTheme();
  const emergency = useEmergencyTrigger(analysis.safety);
  const cardProps = { analysis, pages, handlers };
  const driving = drivingDemand(analysis);
  const phone = firstPrintedPhone(analysis);
  const verifyId = analysis.urgency.verify_resource_id;
  const onRemind = driving && canRemind(driving) && handlers.onRemind ? () => handlers.onRemind?.(driving) : undefined;
  const onVerify = verifyId
    ? handlers.onVerifyResource
      ? () => handlers.onVerifyResource?.(verifyId)
      : undefined
    : phone && handlers.onCall
      ? () => handlers.onCall?.(phone)
      : undefined;
  const disc = disclaimerKey(analysis.disclaimer_kind);
  const banners = resultBanners(analysis, { machineTranslated: meta.machineTranslated, uiTag: meta.tag });
  const asOfNote = sampleAsOfNoteKey(analysis);
  const urgency = useLocalizedUrgency(analysis.urgency);
  const askOff = Boolean(offline || chatUnavailable);
  return (
    <View testID="result-view" style={styles.stack}>
      {emergency.triggered ? (
        <EmergencyCard
          kinds={emergency.kinds}
          triggered
          inline
          onClose={() => undefined}
          onMoreHelp={handlers.onEmergencyMoreHelp}
        />
      ) : null}
      <ScamCard {...cardProps} />
      <WarningChips {...cardProps} />
      <UrgencyBanner urgency={urgency} onRemind={onRemind} onVerify={onVerify} />
      {asOfNote ? (
        <AppText variant="caption" color="textMuted" testID="demo-as-of-note">
          {t(asOfNote)}
        </AppText>
      ) : null}
      {disc ? <SpeakRow text={t(disc)} testID="disclaimer-header" /> : null}
      {banners.map((b) => (
        <Banner key={b.key} kind={TONE_KIND[b.tone]} text={t(b.key, b.vars)} />
      ))}
      <SummaryCard {...cardProps} />
      <DemandsCard {...cardProps} />
      <UnverifiedSection {...cardProps} />
      <PlanCard {...cardProps} />
      <DetailsSection {...cardProps} />
      <GlossaryCard {...cardProps} />
      <QuestionsCard {...cardProps} />
      <RedFlagsCard {...cardProps} />
      <HelpPreview {...cardProps} onSeeAll={handlers.onSeeAllHelp} onSetRegion={handlers.onSetRegion} />
      {handlers.onAsk ? (
        <View style={styles.ask}>
          <BigButton
            label={t('btn.ask')}
            icon="help"
            variant="secondary"
            size={56}
            disabled={askOff}
            onPress={() => handlers.onAsk?.()}
          />
          {offline ? <AppText color="textMuted">{t('state.offline_disabled')}</AppText> : null}
          {chatUnavailable ? (
            <AppText color="textMuted" testID="ask-unavailable">
              {t(CHAT_UNAVAILABLE_KEY)}
            </AppText>
          ) : null}
          {askPrompts(analysis).length && !chatUnavailable ? (
            <View style={[styles.prompts, { flexDirection: dir.row }]}>
              {askPrompts(analysis).map((q, i) => (
                <Pressable
                  key={`${i}-${q}`}
                  testID={`ask-prompt-${i}`}
                  role="button"
                  accessibilityLabel={q}
                  disabled={askOff}
                  onPress={() => handlers.onAsk?.(q)}
                  style={[styles.prompt, { borderColor: colors.primary, opacity: askOff ? 0.5 : 1 }]}>
                  <AppText variant="caption" color="primary" weight="bold" lang={analysis.target_language}>
                    {bt(q)}
                  </AppText>
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
      <View testID="result-footer" style={styles.footer}>
        {footerKeys(analysis).map((k) => (
          <AppText key={k} variant="caption" color="textMuted">
            {t(k)}
          </AppText>
        ))}
        <FeedbackRow
          surface="summary"
          documentType={analysis.document_type}
          documentCategory={analysis.category}
          modelId={analysis.model_meta.model_id}
        />
        {handlers.onReportProblem ? (
          <BigButton label={t('btn.report_problem')} icon="flag" variant="secondary" size={56} onPress={handlers.onReportProblem} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: {
    gap: space.lg,
  },
  ask: {
    gap: space.xs,
  },
  prompts: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  prompt: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    borderWidth: 2,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
  },
  footer: {
    gap: space.sm,
  },
});
