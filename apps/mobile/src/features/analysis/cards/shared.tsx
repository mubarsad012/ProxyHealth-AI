// Shared pieces of the S7 result cards: the handler bundle, the fact row (quote + crop +
// confidence — D-09: every fact is anchored), `SourceText` for words as printed, and the
// kind-icon maps (icons are real objects and are never mirrored in RTL).

import { Pressable, type StyleProp, StyleSheet, type TextStyle, View } from 'react-native';

import type { AnalysisResult, Confidence, Demand, DemandKind, PlanStepKind, ResourceTag } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { ConfidenceChip } from '@/design/components/ConfidenceChip';
import { Crop } from '@/design/components/Crop';
import type { IconName } from '@/design/components/Icon';
import { AppText, type TextVariant, webLangProps } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { resolveAuto } from '@/i18n/bidi';
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

/** BCP-47 tag of the paper's own language, or undefined when the server did not know it. */
export function paperLang(tag: string | null | undefined): string | undefined {
  if (!tag || tag === 'und' || tag === 'unknown') return undefined;
  return tag;
}

/**
 * Accessibility-language props for a control whose label is the paper's own words (a crop whose
 * label is the quote, an S8 block): iOS `accessibilityLanguage`, web `lang`. On web the layout
 * `dir` is passed too, so the tag does not also flip the control's direction.
 */
export function paperLangProps(tag: string | null | undefined, layout: 'ltr' | 'rtl'): Record<string, string> {
  const lang = paperLang(tag);
  if (!lang) return {};
  return { accessibilityLanguage: lang, ...webLangProps(lang, layout) };
}

export interface SourceTextProps {
  /** The words exactly as printed (a quote, `value_verbatim`, `term_as_written`, an S8 block). */
  children: string;
  /** `analysis.detected_language`: screen readers read these words with that voice (WCAG 3.1.2). */
  lang: string | null | undefined;
  /** `ltr` for values (dates, numbers, amounts); `auto` (default) follows the first strong letter. */
  dir?: 'ltr' | 'auto';
  variant?: TextVariant;
  weight?: 'regular' | 'bold';
  style?: StyleProp<TextStyle>;
  testID?: string;
}

/**
 * Words as printed on the paper, bidi-isolated like `<Bidi>` and tagged with the paper's language
 * (`accessibilityLanguage` on native, `lang` on web) so an English quote inside a Dari or Arabic
 * card is not read with the UI language's voice (COMPLIANCE_PRIVACY §15, PRODUCT_SPEC S7).
 */
export function SourceText({ children, lang, dir = 'auto', variant = 'body', weight, style, testID }: SourceTextProps) {
  const layout = useDirection().dir;
  const resolved = dir === 'auto' ? resolveAuto(children, layout) : dir;
  return (
    <AppText
      variant={variant}
      weight={weight}
      align="auto"
      lang={paperLang(lang)}
      testID={testID}
      style={[{ writingDirection: resolved }, style]}>
      <Bidi dir={resolved}>{children}</Bidi>
    </AppText>
  );
}

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
  const lang = analysis.detected_language;
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
        {...paperLangProps(lang, dir.dir)}
        testID={testID ? `${testID}-crop` : undefined}>
        <Crop pageImageUri={image?.uri ?? null} bbox={bbox} quote={quote} width={image?.width} height={image?.height} />
      </Pressable>
      {image ? (
        <View style={[styles.quote, { borderColor: colors.divider }]}>
          <SourceText lang={lang} variant="caption">{`“${quote}”`}</SourceText>
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
