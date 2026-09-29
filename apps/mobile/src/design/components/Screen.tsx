// Screen scaffold (PRODUCT_SPEC §5.7): header with back (mirrored in RTL), title and the calm
// "Need help now?" link to the emergency card on every screen; scrolling body with the 16 pt
// gutter; optional sticky footer (action bar). In clerk mode the header is hidden.

import { type Href, router } from 'expo-router';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon } from '@/design/components/Icon';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { size, space } from '@/design/tokens';
import { useDirection, useRestartPending } from '@/i18n/direction';
import { useI18n } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { useSession } from '@/store/session';

export const EMERGENCY_HREF = '/emergency' as Href;

export interface ScreenProps {
  /** Already-translated title. Omit for screens whose first element is their own heading. */
  title?: string;
  /** Show the back button (stack screens). */
  back?: boolean;
  onBack?(): void;
  children: ReactNode;
  /** Sticky bottom area (e.g. the S7 action bar); content gets matching bottom padding. */
  footer?: ReactNode;
  scroll?: boolean;
  /** Hide the "Need help now?" link (the emergency card itself). */
  hideHelpLink?: boolean;
  testID?: string;
}

export function openEmergency(): void {
  router.push(EMERGENCY_HREF);
}

export function ScreenHeader({ title, back, onBack, hideHelpLink }: Omit<ScreenProps, 'children'>) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const goBack = () => {
    if (onBack) onBack();
    else if (router.canGoBack()) router.back();
    else router.replace('/' as Href);
  };
  return (
    <View style={[styles.header, { flexDirection: dir.row, borderBottomColor: colors.divider }]}>
      {back ? (
        <Pressable
          role="button"
          accessibilityLabel={t('btn.back')}
          hitSlop={size.hitSlop}
          onPress={goBack}
          style={styles.iconButton}>
          <Icon name="arrow-back" color={colors.text} />
        </Pressable>
      ) : null}
      <View style={styles.title}>{title ? <Heading level={1} variant="title">{title}</Heading> : null}</View>
      {hideHelpLink ? null : (
        <Pressable
          role="link"
          accessibilityLabel={t('home.need_help_now')}
          hitSlop={size.hitSlop}
          onPress={openEmergency}
          style={styles.help}>
          <AppText variant="caption" color="link" weight="bold">
            {t('home.need_help_now')}
          </AppText>
        </Pressable>
      )}
    </View>
  );
}

/** Native only (D-26): after switching to/from an RTL pack the layout is already mirrored by
 *  row-reverse; this line asks for a restart to finish, and "Later" dismisses it. */
export function RestartNotice() {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const pending = useRestartPending();
  if (!pending) return null;
  return (
    <View role="status" style={[styles.notice, { flexDirection: dir.row, borderColor: colors.warning }]}>
      <View style={styles.title}>
        <AppText variant="caption">{t('direction.restart_prompt')}</AppText>
      </View>
      <Pressable
        role="button"
        accessibilityLabel={t('btn.restart_later')}
        hitSlop={size.hitSlop}
        onPress={() => useI18n.getState().setRestartPending(false)}
        style={styles.help}>
        <AppText variant="caption" color="link" weight="bold">
          {t('btn.restart_later')}
        </AppText>
      </Pressable>
    </View>
  );
}

export function Screen({ title, back, onBack, children, footer, scroll = true, hideHelpLink, testID }: ScreenProps) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const clerkMode = useSession((s) => s.clerkMode);
  const body = (
    <View style={styles.body}>
      <RestartNotice />
      {children}
    </View>
  );
  return (
    <View testID={testID} style={[styles.root, { backgroundColor: colors.background, paddingTop: insets.top }]}>
      {clerkMode ? null : <ScreenHeader title={title} back={back} onBack={onBack} hideHelpLink={hideHelpLink} />}
      {scroll ? (
        <ScrollView
          contentContainerStyle={[styles.scroll, { paddingBottom: space.xxxl + (footer ? size.primaryCta : 0) }]}
          keyboardShouldPersistTaps="handled">
          {body}
        </ScrollView>
      ) : (
        <View style={[styles.scroll, styles.flex]}>{body}</View>
      )}
      {footer ? (
        <View
          style={[
            styles.footer,
            { borderTopColor: colors.divider, backgroundColor: colors.background, paddingBottom: space.md + insets.bottom },
          ]}>
          {footer}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  header: {
    minHeight: size.button,
    alignItems: 'center',
    gap: space.sm,
    paddingHorizontal: space.screenGutter,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  iconButton: {
    width: size.minTouch,
    height: size.minTouch,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    flex: 1,
  },
  help: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    paddingHorizontal: space.sm,
  },
  scroll: {
    paddingHorizontal: space.screenGutter,
    paddingTop: space.lg,
  },
  body: {
    gap: space.lg,
    width: '100%',
    maxWidth: 720,
    alignSelf: 'center',
  },
  notice: {
    alignItems: 'center',
    gap: space.sm,
    padding: space.sm,
    borderWidth: 1,
    borderRadius: 12,
  },
  footer: {
    paddingHorizontal: space.screenGutter,
    paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
});
