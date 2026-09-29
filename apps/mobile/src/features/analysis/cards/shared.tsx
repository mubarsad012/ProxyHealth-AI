// Shared pieces of the S7 result cards: the handler bundle, the fact row (quote + crop +
// confidence — D-09: every fact is anchored) and the kind-icon maps (icons are real objects and
// are never mirrored in RTL).

import { Pressable, StyleSheet, View } from 'react-native';

import type { AnalysisResult, Confidence, Demand, DemandKind, PlanStepKind, ResourceTag } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { ConfidenceChip } from '@/design/components/ConfidenceChip';
import { Crop } from '@/design/components/Crop';
import type { IconName } from '@/design/components/Icon';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { pageImageFor, pageOfSpans, unionBbox } from '../pageImages';

export interface ResultHandlers {
  /** S8 at a block / page. */
  onOpenSource?(opts: { block?: string; page?: number }): void;
  /** Back to S5 (re-scan a part). */
  onRescan?(): void;
  /** Only ever called for verified, reminder-eligible demands. */
  onRemind?(demand: Demand): void;
  onFindHelp?(tags: ResourceTag[]): void;
  onAsk?(question?: string): void;
  onOpenUrl?(url: string): void;
  onCall?(href: string): void;
}

export interface ResultCardProps {
  analysis: AnalysisResult;
  pages: readonly CapturedPage[];
  handlers: ResultHandlers;
}

export const DEMAND_ICONS: Record<DemandKind, IconName> = {
  deadline: 'calendar',
  relative_deadline: 'calendar',
  amount: 'info',
  document_requested: 'papers',
  appointment: 'calendar-clock',
  action: 'check',
  contact: 'phone',
};

export const PLAN_ICONS: Record<PlanStepKind, IconName> = {
  call: 'phone',
  mail: 'papers',
  bring: 'papers',
  gather: 'papers',
  ask: 'help',
  visit: 'home',
  submit_online: 'globe',
  wait: 'calendar-clock',
  professional: 'people',
  verify: 'check',
};

export interface FactRowProps {
  analysis: AnalysisResult;
  pages: readonly CapturedPage[];
  spanIds: readonly string[];
  page: number;
  quote: string;
  confidence: Confidence;
  handlers: ResultHandlers;
  testID?: string;
}

/** Quote + Crop (full page or quote-only fallback) + ConfidenceChip; tap → S8 at the block. */
export function FactRow({ analysis, pages, spanIds, page, quote, confidence, handlers, testID }: FactRowProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const onPage = pageOfSpans(analysis, spanIds, page);
  const image = pageImageFor(analysis, pages, onPage);
  const bbox = unionBbox(analysis, spanIds, onPage);
  const open = handlers.onOpenSource
    ? () => handlers.onOpenSource?.({ block: spanIds[0], page: onPage })
    : undefined;
  return (
    <View testID={testID} style={styles.fact}>
      <Pressable
        role={open ? 'button' : undefined}
        accessibilityLabel={quote}
        accessibilityHint={t('card.found_on_page', { page: onPage })}
        disabled={!open}
        onPress={open}
        testID={testID ? `${testID}-crop` : undefined}>
        <Crop pageImageUri={image?.uri ?? null} bbox={bbox} quote={quote} width={image?.width} height={image?.height} />
      </Pressable>
      {image ? (
        <View style={[styles.quote, { borderColor: colors.divider }]}>
          <Bidi dir="auto" variant="caption">
            {`“${quote}”`}
          </Bidi>
        </View>
      ) : null}
      <View style={[styles.meta, { flexDirection: dir.row }]}>
        <ConfidenceChip confidence={confidence} onRescan={handlers.onRescan} />
        <AppText variant="caption" color="textMuted">
          {t('card.found_on_page', { page: onPage })}
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  fact: {
    gap: space.sm,
  },
  quote: {
    borderStartWidth: 3,
    paddingHorizontal: space.sm,
    paddingVertical: space.xs,
    borderRadius: radius.sm,
  },
  meta: {
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: space.sm,
  },
});
