// S11 Action Hub for one paper (rendered by WP5's `app/result/[id]/help.tsx`). Emergency card
// first when `safety.emergency`, scam card first when `scam_risk` ≠ none, region control, the
// matched resources with checklist, LSC note + "If that is not you", national fallbacks (from the
// response, or the bundled subset offline), and "Save as quick sheet" → S15.

import { type Href, router } from 'expo-router';
import { useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import type { AnalysisResult, ResourceMatchRequest, ResourceTag } from '@/api/types';
import { AppText, Banner, BigButton, ErrorState } from '@/design/components';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { EmergencyCard, useEmergencyTrigger } from '@/features/emergency';
import { usePackMeta, useT } from '@/i18n/useT';

import { RegionControl, useRegion } from './RegionControl';
import { buildMatchRequestForAnalysis, buildMatchRequestForTags, offlineMatchResponse } from './request';
import { ResourceList } from './ResourceList';
import { useChecklistState } from './useChecklistState';
import { useResourceMatch } from './useResourceMatch';

export interface HelpForDocumentProps {
  analysis: AnalysisResult;
  /** `?focus=<resource_id>` expands one card. */
  focus?: string | null;
  /** `?tags=a,b` from a plan step overrides the paper's tags. */
  tags?: ResourceTag[] | null;
}

export function quickSheetHref(analysisId: string): Href {
  return `/result/${encodeURIComponent(analysisId)}/quicksheet` as Href;
}

export function ScamNotice({ risk }: { risk: 'possible' | 'likely' }) {
  const t = useT();
  const { colors } = useTheme();
  return (
    <View role="alert" style={[styles.scam, { borderColor: colors.danger }]}>
      <AppText weight="bold" color="danger">
        {t(risk === 'likely' ? 'scam.card.likely' : 'scam.card.possible')}
      </AppText>
    </View>
  );
}

export function useLscAlternative(base: ResourceMatchRequest | null) {
  const region = useRegion();
  const [asked, setAsked] = useState(false);
  const req = useMemo(
    () =>
      asked && base
        ? buildMatchRequestForTags(['immigration_legal_help'], { region, language: base.language })
        : null,
    [asked, base, region],
  );
  const alt = useResourceMatch(req);
  return { ask: () => setAsked(true), data: alt.data ?? (req && alt.error ? offlineMatchResponse(req) : null) };
}

export function HelpForDocument({ analysis, focus, tags }: HelpForDocumentProps) {
  const t = useT();
  const meta = usePackMeta();
  const region = useRegion();
  const tagsKey = (tags ?? []).join(',');
  const req = useMemo(
    () =>
      buildMatchRequestForAnalysis(analysis, {
        region,
        language: meta.tag,
        tags: tagsKey ? (tagsKey.split(',') as ResourceTag[]) : null,
      }),
    [analysis, region, meta.tag, tagsKey],
  );
  const match = useResourceMatch(req, { documentId: analysis.analysis_id });
  const lsc = useLscAlternative(req);
  const checks = useChecklistState(analysis.analysis_id);
  const emergency = useEmergencyTrigger(analysis.safety ?? null);
  const [emergencyClosed, setEmergencyClosed] = useState(false);
  const data = match.data ?? (match.error ? offlineMatchResponse(req) : null);

  return (
    <View style={styles.wrap} testID="help-for-document">
      {emergency.triggered && !emergencyClosed ? (
        <EmergencyCard kinds={emergency.kinds} onClose={() => setEmergencyClosed(true)} />
      ) : null}
      {analysis.scam_risk && analysis.scam_risk !== 'none' ? <ScamNotice risk={analysis.scam_risk} /> : null}
      <RegionControl />
      {match.offline ? (
        match.cached ? (
          <AppText color="textMuted">{t('help.offline_cached')}</AppText>
        ) : (
          <Banner kind="offline" />
        )
      ) : null}
      {match.error && !match.offline ? <ErrorState error={match.error} onRetry={match.refresh} /> : null}
      {match.loading && !data ? <LoadingCards /> : null}
      {data ? (
        <ResourceList
          data={data}
          regionKnown={Boolean(region.state)}
          checkState={checks.state}
          onToggleCheck={checks.toggle}
          focusId={focus ?? null}
          onLscAlternative={lsc.ask}
          lscAlternative={lsc.data}
        />
      ) : null}
      <BigButton
        label={t('btn.save_quick_sheet')}
        icon="papers"
        variant="secondary"
        size={56}
        onPress={() => router.push(quickSheetHref(analysis.analysis_id))}
      />
    </View>
  );
}

/** Loading skeleton: three quiet placeholder blocks (no spinner text to read out). */
export function LoadingCards() {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap} accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
      {[0, 1, 2].map((i) => (
        <View key={i} style={[styles.skeleton, { backgroundColor: colors.surface, borderColor: colors.divider }]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  scam: {
    borderWidth: 2,
    borderRadius: radius.lg,
    padding: space.lg,
  },
  skeleton: {
    height: 120,
    borderRadius: radius.lg,
    borderWidth: 1,
  },
});
