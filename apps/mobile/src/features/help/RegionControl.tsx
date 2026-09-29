// "Where you live: {state} {zip3}" → Settings (S17). State + optional ZIP3 only; never GPS,
// never a full ZIP (D-24). Unset → `help.set_region_prompt`.

import { type Href, router } from 'expo-router';
import { useMemo } from 'react';

import { LinkRow } from '@/design/components';
import { useT } from '@/i18n/useT';
import { useSettings } from '@/store/settings';

import type { Region } from './request';

export const SETTINGS_HREF = '/settings' as Href;

export function useRegion(): Region {
  const state = useSettings((s) => s.region.state);
  const zip3 = useSettings((s) => s.region.zip3);
  return useMemo(() => ({ state: state ?? null, zip3: zip3 ?? null }), [state, zip3]);
}

export function RegionControl() {
  const t = useT();
  const region = useRegion();
  const label = region.state
    ? t('help.region', { state: region.state, zip3: region.zip3 ?? '' }).trim()
    : t('help.set_region_prompt');
  return <LinkRow label={label} onPress={() => router.push(SETTINGS_HREF)} testID="help-region" />;
}
