// S11 on the Get help tab (no document): region control, need tiles → matched resources, and
// "See all help" (GET /v1/resources for browsing). Offline: bundled national subset only.
// "Someone is in danger" also opens the emergency card (S19).

import { useEffect, useMemo, useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { useApi } from '@/api/config';
import { type ApiError, toApiError } from '@/api/errors';
import type { Resource, ResourceMatchResponse, ResourceTag } from '@/api/types';
import { Banner, BigButton, ErrorState, Heading, openEmergency, Screen } from '@/design/components';
import { space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';

import { LoadingCards, useLscAlternative } from './HelpForDocument';
import { NEED_TILES, type NeedTile } from './needs';
import { RegionControl, useRegion } from './RegionControl';
import { buildMatchRequestForTags, bundledResources, offlineMatchResponse } from './request';
import { ResourceCard } from './ResourceCard';
import { ResourceList } from './ResourceList';
import { useChecklistState } from './useChecklistState';
import { isOfflineError, useResourceMatch } from './useResourceMatch';

export interface HelpTabScreenProps {
  /** `?tags=a,b` deep link (e.g. from a troubleshoot "Ask a person"). */
  initialTags?: ResourceTag[] | null;
  focus?: string | null;
}

interface BrowseState {
  key: string;
  items: Resource[];
  error: ApiError | null;
}

function useBrowse(enabled: boolean, state: string | null, language: string) {
  const client = useApi();
  const key = enabled ? `${state ?? ''}|${language}` : '';
  const [result, setResult] = useState<BrowseState | null>(null);
  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    client
      .listResources({ state: state ?? undefined, language, limit: 50 })
      .then((res) => {
        if (!cancelled) setResult({ key, items: res.items, error: null });
      })
      .catch((e: unknown) => {
        if (!cancelled) setResult({ key, items: bundledResources(), error: toApiError(e) });
      });
    return () => {
      cancelled = true;
    };
  }, [client, key, state, language]);
  const current = result && result.key === key ? result : null;
  return { loading: Boolean(key) && !current, items: current?.items ?? [], error: current?.error ?? null };
}

export function HelpTabScreen({ initialTags, focus }: HelpTabScreenProps) {
  const t = useT();
  const dir = useDirection();
  const meta = usePackMeta();
  const region = useRegion();
  const [need, setNeed] = useState<NeedTile | null>(null);
  const [browsing, setBrowsing] = useState(false);
  const initialKey = (initialTags ?? []).join(',');
  const req = useMemo(() => {
    const tags = need ? need.tags : initialKey ? (initialKey.split(',') as ResourceTag[]) : [];
    return buildMatchRequestForTags(tags, {
      region,
      language: meta.tag,
      scamRisk: need?.scam ? 'possible' : undefined,
      emergency: need?.emergency,
    });
  }, [need, initialKey, region, meta.tag]);
  const match = useResourceMatch(req);
  const lsc = useLscAlternative(req);
  const checks = useChecklistState(null);
  const browse = useBrowse(browsing, region.state, meta.tag);
  const data: ResourceMatchResponse | null = match.data ?? (req && match.error ? offlineMatchResponse(req) : null);

  const pick = (tile: NeedTile) => {
    setBrowsing(false);
    setNeed(tile);
    if (tile.emergency) openEmergency();
  };

  return (
    <Screen title={t('tabs.help')} testID="help-tab">
      <View style={styles.wrap}>
        <RegionControl />
        <View style={[styles.tiles, { flexDirection: dir.row }]} role="list">
          {NEED_TILES.map((tile) => (
            <View key={tile.id} style={styles.tile} role="listitem">
              <BigButton
                label={t(tile.key)}
                icon={tile.icon}
                variant={need?.id === tile.id ? 'primary' : 'secondary'}
                size={56}
                onPress={() => pick(tile)}
                testID={`need-${tile.id}`}
              />
            </View>
          ))}
        </View>
        <BigButton
          label={t('help.see_all')}
          icon="search"
          variant={browsing ? 'primary' : 'secondary'}
          size={56}
          onPress={() => {
            setNeed(null);
            setBrowsing(true);
          }}
          testID="help-see-all"
        />
        {match.offline || (browsing && isOfflineError(browse.error)) ? <Banner kind="offline" /> : null}
        {match.error && !match.offline ? <ErrorState error={match.error} onRetry={match.refresh} /> : null}
        {req && match.loading && !data ? <LoadingCards /> : null}
        {req && data && !browsing ? (
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
        {browsing ? (
          <View style={styles.wrap} testID="help-browse">
            <Heading level={2}>{t('help.see_all')}</Heading>
            {browse.loading ? <LoadingCards /> : null}
            {browse.items
              .filter((r) => r.link_health !== 'broken')
              .map((r) => (
                <ResourceCard key={r.id} resource={r} eligibilityNoteKey={r.status_note_key} onLscAlternative={lsc.ask} />
              ))}
          </View>
        ) : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.lg,
  },
  tiles: {
    flexWrap: 'wrap',
    gap: space.sm,
  },
  tile: {
    flexGrow: 1,
    flexBasis: 240,
  },
});
