// J-F / S16: the reporting resources that follow the fixed scam card — fetched with
// `POST /v1/resources/match {tags: ["scam_report"], scam_risk, language}`. Phones and URLs come
// from the vetted DB only (server response, or the bundled subset offline: DHS OIG, FTC), never
// from the model's text about the screenshot.

import { useMemo } from 'react';
import { StyleSheet, View } from 'react-native';

import type { Resource, ResourceMatchResponse, ScamRisk } from '@/api/types';
import { space } from '@/design/tokens';
import { LoadingCards } from '@/features/help/HelpForDocument';
import { isVisible } from '@/features/help/format';
import { useRegion } from '@/features/help/RegionControl';
import { buildMatchRequestForTags, offlineMatchResponse } from '@/features/help/request';
import { ResourceCard } from '@/features/help/ResourceCard';
import { useResourceMatch } from '@/features/help/useResourceMatch';
import { usePackMeta } from '@/i18n/useT';

export const MAX_REPORT_RESOURCES = 3;

/** `scam_report` entries first (matched results, then national fallbacks), de-duplicated. */
export function reportingResources(data: ResourceMatchResponse | null, max: number = MAX_REPORT_RESOURCES): Resource[] {
  if (!data) return [];
  const all = [...(data.results ?? []).map((m) => m.resource), ...(data.national_fallbacks ?? [])].filter(isVisible);
  const seen = new Set<string>();
  const unique = all.filter((r) => (seen.has(r.id) ? false : (seen.add(r.id), true)));
  const reporting = unique.filter((r) => r.tags.includes('scam_report'));
  return (reporting.length ? reporting : unique).slice(0, max);
}

export function ScamReportResources({ risk }: { risk: Exclude<ScamRisk, 'none'> }) {
  const meta = usePackMeta();
  const region = useRegion();
  const req = useMemo(
    () => buildMatchRequestForTags(['scam_report'], { region, language: meta.tag, scamRisk: risk }),
    [region, meta.tag, risk],
  );
  const match = useResourceMatch(req);
  const data = match.data ?? (req && match.error ? offlineMatchResponse(req) : null);
  const resources = reportingResources(data);
  if (match.loading && !resources.length) return <LoadingCards />;
  if (!resources.length) return null;
  return (
    <View style={styles.list} testID="scam-report-resources">
      {resources.map((r, i) => (
        <ResourceCard key={r.id} resource={r} eligibilityNoteKey={r.status_note_key} primary={i === 0} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: {
    gap: space.md,
  },
});
