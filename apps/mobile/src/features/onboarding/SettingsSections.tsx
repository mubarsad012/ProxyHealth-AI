// Settings sections owned by WP4's `(tabs)/settings.tsx` (PRODUCT_SPEC S17 items 3, 9, 10): region
// (state + optional zip3 — never a full ZIP, never GPS, D-24), about (versions, models, the fixed
// "what it does not do" list) and the developer section (non-production builds only).

import { useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';

import { useApi } from '@/api/config';
import type { FeedbackKind, ServerConfig } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { BigButton } from '@/design/components/BigButton';
import { Collapsible } from '@/design/components/Collapsible';
import { ExternalLink } from '@/design/components/ExternalLink';
import { Interpolated } from '@/design/components/Interpolated';
import { ChoiceChips, SettingsSection } from '@/design/components/SettingsRows';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { appVersion, buildFeedbackRequest, NEGATIVE_KINDS } from '@/design/components/FeedbackRow';
import { useDirection } from '@/i18n/direction';
import { useI18n } from '@/i18n/store';
import { usePackMeta, useT } from '@/i18n/useT';
import { type UiTier, useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

/** USPS codes: 50 states, DC, PR and the territories (PRODUCT_SPEC S17 item 3). Proper nouns. */
export const US_STATES: readonly [string, string][] = [
  ['AL', 'Alabama'], ['AK', 'Alaska'], ['AZ', 'Arizona'], ['AR', 'Arkansas'], ['CA', 'California'],
  ['CO', 'Colorado'], ['CT', 'Connecticut'], ['DE', 'Delaware'], ['DC', 'District of Columbia'],
  ['FL', 'Florida'], ['GA', 'Georgia'], ['HI', 'Hawaii'], ['ID', 'Idaho'], ['IL', 'Illinois'],
  ['IN', 'Indiana'], ['IA', 'Iowa'], ['KS', 'Kansas'], ['KY', 'Kentucky'], ['LA', 'Louisiana'],
  ['ME', 'Maine'], ['MD', 'Maryland'], ['MA', 'Massachusetts'], ['MI', 'Michigan'], ['MN', 'Minnesota'],
  ['MS', 'Mississippi'], ['MO', 'Missouri'], ['MT', 'Montana'], ['NE', 'Nebraska'], ['NV', 'Nevada'],
  ['NH', 'New Hampshire'], ['NJ', 'New Jersey'], ['NM', 'New Mexico'], ['NY', 'New York'],
  ['NC', 'North Carolina'], ['ND', 'North Dakota'], ['OH', 'Ohio'], ['OK', 'Oklahoma'], ['OR', 'Oregon'],
  ['PA', 'Pennsylvania'], ['RI', 'Rhode Island'], ['SC', 'South Carolina'], ['SD', 'South Dakota'],
  ['TN', 'Tennessee'], ['TX', 'Texas'], ['UT', 'Utah'], ['VT', 'Vermont'], ['VA', 'Virginia'],
  ['WA', 'Washington'], ['WV', 'West Virginia'], ['WI', 'Wisconsin'], ['WY', 'Wyoming'],
  ['PR', 'Puerto Rico'], ['GU', 'Guam'], ['VI', 'U.S. Virgin Islands'], ['AS', 'American Samoa'],
  ['MP', 'Northern Mariana Islands'],
];

/** Keep only three digits (never a full ZIP). */
export function sanitizeZip3(input: string): string | null {
  const digits = input.replace(/\D/g, '').slice(0, 3);
  return digits.length === 3 ? digits : null;
}

export function RegionSection() {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const region = useSettings((s) => s.region);
  const setRegion = useSettings((s) => s.setRegion);
  const [zip, setZip] = useState(region.zip3 ?? '');
  return (
    <SettingsSection title={t('settings.region')} testID="settings-region">
      <Collapsible title={region.state ? (US_STATES.find(([c]) => c === region.state)?.[1] ?? region.state) : t('settings.state_none')}>
        <ChoiceChips
          options={[{ value: '', label: t('settings.state_none') }, ...US_STATES.map(([code, name]) => ({ value: code, label: name }))]}
          value={region.state ?? ''}
          onChange={(v) => setRegion({ state: v === '' ? null : v })}
        />
      </Collapsible>
      <AppText weight="bold">{t('settings.zip3')}</AppText>
      <TextInput
        testID="settings-zip3"
        value={zip}
        inputMode="numeric"
        keyboardType="number-pad"
        maxLength={3}
        onChangeText={(v) => {
          const digits = v.replace(/\D/g, '').slice(0, 3);
          setZip(digits);
          setRegion({ zip3: sanitizeZip3(digits) });
        }}
        accessibilityLabel={t('settings.zip3')}
        accessibilityHint={t('settings.zip3_why')}
        style={[styles.input, { color: colors.text, borderColor: colors.border, textAlign: dir.textAlign }]}
      />
      <AppText variant="caption" color="textMuted">
        {t('settings.zip3_why')}
      </AppText>
      <BigButton
        label={t('btn.clear_region')}
        variant="secondary"
        size={56}
        onPress={() => {
          setZip('');
          setRegion({ state: null, zip3: null });
        }}
      />
    </SettingsSection>
  );
}

function VersionLine({ text }: { text: string }) {
  return (
    <Bidi dir="ltr" variant="caption">
      {text}
    </Bidi>
  );
}

/** A version row: translated label, the version value LTR-isolated (S17 "RTL"). */
function VersionRow({ labelKey, version }: { labelKey: string; version: string }) {
  const t = useT();
  return <Interpolated template={t(labelKey)} vars={{ version }} ltrKeys={['version']} variant="caption" />;
}

/**
 * S17 item 9 "Report a problem": the fixed feedback kinds only (no free text, D-31). The surface is
 * `app` (CL-057): this report is about the app, not an AI summary, as on S18 (NotFoundScreen).
 */
function ReportProblem() {
  const t = useT();
  const api = useApi();
  const meta = usePackMeta();
  const [sent, setSent] = useState(false);
  if (sent) {
    return (
      <AppText role="status" color="textMuted">
        {t('feedback.thanks')}
      </AppText>
    );
  }
  const send = (kind: FeedbackKind) => {
    setSent(true);
    api.feedback(buildFeedbackRequest({ surface: 'app' }, kind, meta.tag)).catch(() => undefined);
  };
  return (
    <Collapsible title={t('btn.report_problem')}>
      <AppText weight="bold">{t('feedback.what_wrong')}</AppText>
      {NEGATIVE_KINDS.map((k) => (
        <BigButton key={k} label={t(`feedback.kind.${k}`)} variant="secondary" size={56} onPress={() => send(k)} />
      ))}
    </Collapsible>
  );
}

export interface AboutSectionProps {
  config: ServerConfig | null;
  /** The config came from the device cache (server unreachable): rows are marked `state.cached`. */
  cached?: boolean;
}

export function AboutSection({ config, cached = false }: AboutSectionProps) {
  const t = useT();
  const pack = useI18n((s) => s.pack);
  const packVersion = (pack.pack_version ?? config?.base_pack_version ?? 'en').slice(0, 8);
  return (
    <SettingsSection title={t('settings.about')} testID="settings-about">
      <AppText weight="bold">{t('app.name')}</AppText>
      <Interpolated template={t('settings.version')} vars={{ version: appVersion() }} ltrKeys={['version']} />
      <VersionRow labelKey="settings.pack_version" version={packVersion} />
      {pack.reviewed_by ? <AppText>{t('settings.reviewed_by', { name: pack.reviewed_by })}</AppText> : null}
      {config ? (
        <>
          {cached ? (
            <AppText variant="caption" color="textMuted" testID="settings-about-cached">
              {t('state.cached')}
            </AppText>
          ) : null}
          <VersionRow labelKey="settings.contract_version" version={String(config.contract_version)} />
          <VersionRow labelKey="settings.resources_version" version={config.resource_db_version} />
          <VersionRow labelKey="settings.rules_version" version={config.rules_version} />
          <Interpolated
            template={t('settings.models')}
            vars={{ pro: config.models.pro, fast: config.models.fast }}
            ltrKeys={['pro', 'fast']}
          />
        </>
      ) : null}
      <View role="list" style={styles.list}>
        {[1, 2, 3, 4, 5, 6, 7].map((n) => (
          <AppText key={n} role="listitem">
            {t(`about.not.${n}`)}
          </AppText>
        ))}
      </View>
      <ReportProblem />
      {config?.privacy_policy_url ? <ExternalLink href={config.privacy_policy_url}>{t('btn.privacy')}</ExternalLink> : null}
    </SettingsSection>
  );
}

export interface DeveloperSectionProps {
  apiUrl: string;
  config: ServerConfig | null;
  getInstallId(): Promise<string>;
  rotateInstallId(): Promise<string>;
}

const PREVIEW_TIERS: UiTier[] = ['paid', 'unpaid', 'demo', 'unknown'];

export function DeveloperSection({ apiUrl, config, getInstallId, rotateInstallId }: DeveloperSectionProps) {
  const t = useT();
  const tier = useSession((s) => s.tier);
  const setTier = useSession((s) => s.setTier);
  const [installId, setInstallId] = useState<string | null>(null);
  return (
    <SettingsSection title={t('settings.developer')} testID="settings-developer">
      <AppText weight="bold">{t('settings.developer_api_url')}</AppText>
      <VersionLine text={apiUrl} />
      {installId ? <VersionLine text={installId} /> : null}
      <BigButton
        label={t('btn.rotate_install_id')}
        variant="secondary"
        size={56}
        onPress={() => {
          void (installId ? rotateInstallId() : getInstallId()).then(setInstallId);
        }}
      />
      <ChoiceChips
        options={PREVIEW_TIERS.map((v) => ({ value: v, label: t(`consent.badge.${v}`) }))}
        value={tier === 'mixed' ? 'unpaid' : tier === 'none' ? 'unknown' : tier}
        onChange={(v) => setTier(v)}
      />
      {config ? (
        <Collapsible title="ServerConfig">
          <Bidi dir="ltr" variant="caption">
            {JSON.stringify({ ...config, languages: `${config.languages?.length ?? 0} languages` }, null, 2)}
          </Bidi>
        </Collapsible>
      ) : null}
    </SettingsSection>
  );
}

const styles = StyleSheet.create({
  input: {
    minHeight: size.button,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: space.md,
    fontSize: 18,
  },
  list: {
    gap: space.sm,
  },
});
