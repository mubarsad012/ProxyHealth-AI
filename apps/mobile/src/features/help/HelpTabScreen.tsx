// S11 on the Get help tab (no document): region control, the language filter chip (default = the
// UI language; the choice is what the match / browse requests send), the search box
// (`GET /v1/resources?q=…`, by name), need tiles → matched resources, and "See all help"
// (`GET /v1/resources` for browsing). Offline: bundled national subset only (search filters it
// locally by the server's own name rule). "Someone is in danger" also opens the emergency card (S19).

import { useEffect, useMemo, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import type { ResourceMatchResponse, ResourceTag } from '@/api/types';
import { AppText, Banner, BigButton, ErrorState, Heading, openEmergency, Screen } from '@/design/components';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';

import { browseLanguage, MAX_QUERY_CHARS, matchLanguage, normaliseQuery, useBrowse } from './browse';
import { LoadingCards, useLscAlternative } from './HelpForDocument';
import { LanguageFilter } from './LanguageFilter';
import { NEED_TILES, type NeedTile } from './needs';
import { RegionControl, useRegion } from './RegionControl';
import { buildMatchRequestForTags, offlineMatchResponse } from './request';
import { ResourceCard } from './ResourceCard';
import { ResourceList } from './ResourceList';
import { useChecklistState } from './useChecklistState';
import { isOfflineError, useResourceMatch } from './useResourceMatch';

export interface HelpTabScreenProps {
  /** `?tags=a,b` deep link (e.g. from a troubleshoot "Ask a person"). */
  initialTags?: ResourceTag[] | null;
  focus?: string | null;
}

/** Typing pauses this long before a search request is sent (Enter searches at once). */
export const SEARCH_DEBOUNCE_MS = 400;
export const SEARCH_EMPTY_KEY = 'help.search_empty';

/** `value` after it stopped changing for `ms` (the latest value wins). */
function useDebounced(value: string, ms: number): [string, (v: string) => void] {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    if (value === settled) return undefined;
    const timer = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(timer);
  }, [value, settled, ms]);
  return [settled, setSettled];
}

export function HelpTabScreen({ initialTags, focus }: HelpTabScreenProps) {
  const t = useT();
  const dir = useDirection();
  const { colors, textFactor } = useTheme();
  const meta = usePackMeta();
  const region = useRegion();
  const [need, setNeed] = useState<NeedTile | null>(null);
  const [browsing, setBrowsing] = useState(false);
  // Language filter chip: null = follow the UI language (also after a language switch).
  const [languagePick, setLanguagePick] = useState<string | null>(null);
  const language = languagePick ?? meta.tag;
  const [text, setText] = useState('');
  const [settledText, settle] = useDebounced(text, SEARCH_DEBOUNCE_MS);
  const query = normaliseQuery(settledText);
  const searching = query !== null;
  const initialKey = (initialTags ?? []).join(',');
  const req = useMemo(() => {
    const tags = need ? need.tags : initialKey ? (initialKey.split(',') as ResourceTag[]) : [];
    return buildMatchRequestForTags(tags, {
      region,
      language: matchLanguage(language, meta.tag),
      scamRisk: need?.scam ? 'possible' : undefined,
      emergency: need?.emergency,
    });
  }, [need, initialKey, region, language, meta.tag]);
  const match = useResourceMatch(searching ? null : req);
  const lsc = useLscAlternative(req);
  const checks = useChecklistState(null);
  const listing = searching || browsing;
  const browse = useBrowse(listing, { state: region.state, language: browseLanguage(language), q: query });
  const data: ResourceMatchResponse | null = match.data ?? (req && match.error ? offlineMatchResponse(req) : null);
  const shown = browse.items.filter((r) => r.link_health !== 'broken');

  const pick = (tile: NeedTile) => {
    setBrowsing(false);
    setText('');
    settle('');
    setNeed(tile);
    if (tile.emergency) openEmergency();
  };

  return (
    <Screen title={t('tabs.help')} testID="help-tab">
      <View style={styles.wrap}>
        <RegionControl />
        <LanguageFilter value={languagePick ?? meta.tag} uiTag={meta.tag} onChange={(tag) => setLanguagePick(tag === meta.tag ? null : tag)} />
        <View style={styles.field}>
          <AppText weight="bold" nativeID="help-search-label">
            {t('help.search')}
          </AppText>
          <TextInput
            testID="help-search"
            value={text}
            onChangeText={(v) => setText(Array.from(v).slice(0, MAX_QUERY_CHARS).join(''))}
            onSubmitEditing={() => settle(text)}
            maxLength={MAX_QUERY_CHARS}
            returnKeyType="search"
            autoCorrect={false}
            accessibilityLabel={t('help.search')}
            aria-labelledby="help-search-label"
            role="searchbox"
            style={[
              styles.input,
              {
                borderColor: colors.border,
                color: colors.text,
                backgroundColor: colors.surfaceRaised,
                textAlign: dir.textAlign,
                writingDirection: dir.writingDirection,
                fontSize: Math.round(18 * textFactor),
              },
            ]}
          />
        </View>
        <View style={[styles.tiles, { flexDirection: dir.row }]} role="list">
          {NEED_TILES.map((tile) => (
            <View key={tile.id} style={styles.tile} role="listitem">
              <BigButton
                label={t(tile.key)}
                icon={tile.icon}
                variant={need?.id === tile.id && !listing ? 'primary' : 'secondary'}
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
          variant={browsing && !searching ? 'primary' : 'secondary'}
          size={56}
          onPress={() => {
            setNeed(null);
            setText('');
            settle('');
            setBrowsing(true);
          }}
          testID="help-see-all"
        />
        {(!listing && match.offline) || (listing && isOfflineError(browse.error)) ? <Banner kind="offline" /> : null}
        {!listing && match.error && !match.offline ? <ErrorState error={match.error} onRetry={match.refresh} /> : null}
        {!listing && req && match.loading && !data ? <LoadingCards /> : null}
        {!listing && req && data ? (
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
        {listing ? (
          <View style={styles.wrap} testID={searching ? 'help-search-results' : 'help-browse'}>
            <Heading level={2}>{searching ? t('help.search') : t('help.see_all')}</Heading>
            {browse.loading ? <LoadingCards /> : null}
            {!browse.loading && shown.length === 0 ? (
              <AppText role="status" testID="help-search-empty">
                {t(SEARCH_EMPTY_KEY)}
              </AppText>
            ) : null}
            {shown.map((r) => (
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
  field: {
    gap: space.xs,
  },
  input: {
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
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
