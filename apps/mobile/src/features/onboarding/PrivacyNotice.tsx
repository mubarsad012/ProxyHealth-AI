// In-app privacy notice (COMPLIANCE_PRIVACY §4.5): opened by `consent.read_more` on S2 and by
// Settings → "How your paper is handled". One screen, plain words, a speaker after every line; the
// last row opens `privacy_policy_url` from `/v1/config` (omitted while the server is unreachable).

import { Modal, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BigButton } from '@/design/components/BigButton';
import { ExternalLink } from '@/design/components/ExternalLink';
import { SpeakButton } from '@/design/components/SpeakButton';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import { platformName } from '@/lib/platform';
import { useSession, type UiTier } from '@/store/session';

import { type AiCopyInput, consentVars, tierCopy, viewTier } from './consentModel';

/** The notice's line keys in order (COMPLIANCE_PRIVACY §4.5 items 1–11), chosen like S2's lines
 *  (`tierCopy`, free-ai-providers §5.2). Item 1 is left out where S2 has no line 1: on the demo tier
 *  nothing reaches an AI service and `consent.line2.demo` says so (Phase 2B). On `local` item 1 is
 *  `privacy.notice.sent.local`, followed by `privacy.notice.model.local`; on `attested` and on
 *  `unpaid` with another vendor, `privacy.notice.sent` (which names Google) is replaced by S2's own
 *  `consent.line1.vendor`. Pass `consentVars(ai)` to `t()` for `{model}` / `{vendor}`. */
export function privacyNoticeKeys(
  tier: UiTier,
  platform: 'ios' | 'android' | 'web',
  ai?: AiCopyInput | null,
): string[] {
  const copy = tierCopy(viewTier(tier), ai);
  return [
    ...(copy.noticeSent ? [copy.noticeSent] : []),
    ...copy.noticeExtra,
    copy.line2,
    'privacy.notice.what_we_keep',
    platform === 'web' ? 'privacy.notice.device_web' : 'privacy.notice.device',
    'privacy.notice.hide_parts',
    'privacy.notice.no_status',
    'privacy.notice.no_ads',
    'privacy.notice.settings_sent',
    'privacy.notice.install_id',
    'privacy.notice.feedback',
    'privacy.notice.delete',
  ];
}

export interface PrivacyNoticeProps {
  visible: boolean;
  onClose(): void;
}

export function PrivacyNoticeContent() {
  const t = useT();
  const dir = useDirection();
  const meta = usePackMeta();
  const tier = useSession((s) => s.tier);
  const config = useSession((s) => s.serverConfig);
  const policyUrl = config?.privacy_policy_url ?? null;
  const vars = consentVars(config);
  return (
    <View style={styles.list}>
      {privacyNoticeKeys(tier, platformName(), config).map((key) => (
        <View key={key} testID={`privacy-notice-${key}`} style={[styles.row, { flexDirection: dir.row }]}>
          <View style={styles.text}>
            <AppText>{t(key, vars)}</AppText>
          </View>
          <SpeakButton text={t(key, vars)} lang={meta.tag} />
        </View>
      ))}
      {policyUrl ? <ExternalLink href={policyUrl}>{t('privacy.notice.full_policy')}</ExternalLink> : null}
    </View>
  );
}

export function PrivacyNotice({ visible, onClose }: PrivacyNoticeProps) {
  const t = useT();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} transparent={false}>
      <View style={[styles.root, { backgroundColor: colors.background, paddingTop: insets.top + space.lg }]}>
        <ScrollView contentContainerStyle={styles.scroll}>
          <Heading level={1}>{t('settings.data')}</Heading>
          <PrivacyNoticeContent />
        </ScrollView>
        <View style={[styles.footer, { paddingBottom: insets.bottom + space.md }]}>
          <BigButton label={t('btn.close')} variant="primary" size={56} onPress={onClose} />
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  scroll: {
    paddingHorizontal: space.screenGutter,
    gap: space.lg,
    paddingBottom: space.xxl,
  },
  list: {
    gap: space.md,
  },
  row: {
    alignItems: 'center',
    gap: space.md,
  },
  text: {
    flex: 1,
  },
  footer: {
    paddingHorizontal: space.screenGutter,
    paddingTop: space.md,
  },
});
