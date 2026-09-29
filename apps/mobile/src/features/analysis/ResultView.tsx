// S7 result body in the FIXED order of PRODUCT_SPEC S7: emergency card (first when triggered) →
// scam card → warning chips → urgency banner → disclaimer header → banners → Card 1 → Card 2 →
// unverified section → Card 3 → details → glossary → questions → red flags → help preview →
// ask → footer (AI-generated + verify-with-sender + "Was this clear?").

import { StyleSheet, View } from 'react-native';

import type { AnalysisResult } from '@/api/types';
import { Banner, type BannerKind } from '@/design/components/Banner';
import { BigButton } from '@/design/components/BigButton';
import { FeedbackRow } from '@/design/components/FeedbackRow';
import { AppText } from '@/design/components/Text';
import { UrgencyBanner } from '@/design/components/UrgencyBanner';
import { space } from '@/design/tokens';
import { EmergencyCard, useEmergencyTrigger } from '@/features/emergency';
import { SpeakRow } from '@/features/speech/SpeakRow';
import { usePackMeta, useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { canRemind, DemandsCard } from './cards/DemandsCard';
import { DetailsSection } from './cards/DetailsSection';
import { HelpPreview } from './cards/HelpPreview';
import { GlossaryCard, QuestionsCard } from './cards/InfoCards';
import { PlanCard } from './cards/PlanCard';
import { RedFlagsCard, ScamCard, WarningChips } from './cards/SafetyCards';
import type { ResultHandlers } from './cards/shared';
import { SummaryCard } from './cards/SummaryCard';
import { disclaimerKey, FOOTER_KEYS, resultBanners, type BannerSpec } from './disclaimers';
import { UnverifiedSection } from './unverifiedSection';
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
}

const TONE_KIND: Record<BannerSpec['tone'], BannerKind> = {
  danger: 'unpaid',
  warning: 'machine_translation',
  info: 'demo',
};

export function ResultView({ analysis, pages, handlers, offline }: ResultViewProps) {
  const t = useT();
  const meta = usePackMeta();
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
      <UrgencyBanner urgency={analysis.urgency} onRemind={onRemind} onVerify={onVerify} />
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
            disabled={offline}
            onPress={() => handlers.onAsk?.()}
          />
          {offline ? <AppText color="textMuted">{t('state.offline_disabled')}</AppText> : null}
        </View>
      ) : null}
      <View testID="result-footer" style={styles.footer}>
        {FOOTER_KEYS.map((k) => (
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
  footer: {
    gap: space.sm,
  },
});
