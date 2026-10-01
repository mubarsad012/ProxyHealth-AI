// Screen scaffold (PRODUCT_SPEC §5.7): a fixed header bar with back (mirrored in RTL) and the calm
// "Need help now?" link to the emergency card on every screen; the screen title as the first thing
// in the scrolling body (so large text can never make the fixed area fill the screen — WCAG
// 1.4.4 / 1.4.10 at the app's "Very large" setting and 200 % OS text); the pack provenance
// banners (machine-translated / partly English pack) on every screen (COMPLIANCE_PRIVACY §5.2,
// D-25); scrolling body with the 16 pt gutter; optional sticky footer (action bar) that never takes
// more than half the screen. In clerk mode the header and the provenance banners are hidden.

import { type Href, router } from 'expo-router';
import { type ReactNode, useCallback, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Banner, PackBannerScope, type PackBannerKind, type PackBannerScopeValue } from '@/design/components/Banner';
import { Icon } from '@/design/components/Icon';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { size, space } from '@/design/tokens';
import { useDirection, useRestartPending } from '@/i18n/direction';
import { useI18n } from '@/i18n/store';
import { usePackMeta, useT } from '@/i18n/useT';
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

export type ScreenHeaderProps = Pick<ScreenProps, 'back' | 'onBack' | 'hideHelpLink'>;

export function openEmergency(): void {
  router.push(EMERGENCY_HREF);
}

/** The fixed bar: back and the help link only. The link may wrap but never takes more than half
 *  the row, and the bar holds no title, so its height stays small at any text size. */
export function ScreenHeader({ back, onBack, hideHelpLink }: ScreenHeaderProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const goBack = () => {
    if (onBack) onBack();
    else if (router.canGoBack()) router.back();
    else router.replace('/' as Href);
  };
  if (!back && hideHelpLink) return null;
  return (
    <View testID="screen-header" style={[styles.header, { flexDirection: dir.row, borderBottomColor: colors.divider }]}>
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
      <View style={styles.spacer} />
      {hideHelpLink ? null : (
        <Pressable
          testID="screen-help-link"
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
      <View style={styles.flex}>
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

type PackBannerCounts = Record<PackBannerKind, number>;

/** The machine-translation / partial-pack lines for the active pack, unless the screen shows them. */
function PackBanners({ shownByScreen }: { shownByScreen: PackBannerCounts }) {
  const meta = usePackMeta();
  const mt = meta.machineTranslated && shownByScreen.machine_translation === 0;
  const partial = meta.partial && shownByScreen.partial_pack === 0;
  if (!mt && !partial) return null;
  return (
    // The scaffold's own banners must not register themselves (they would hide themselves).
    <PackBannerScope.Provider value={null}>
      {mt ? <Banner kind="machine_translation" /> : null}
      {partial ? <Banner kind="partial_pack" /> : null}
    </PackBannerScope.Provider>
  );
}

function usePackBannerScope(): [PackBannerCounts, PackBannerScopeValue] {
  const [counts, setCounts] = useState<PackBannerCounts>({ machine_translation: 0, partial_pack: 0 });
  const bump = useCallback((kind: PackBannerKind, by: number) => {
    setCounts((c) => ({ ...c, [kind]: Math.max(0, c[kind] + by) }));
  }, []);
  const scope = useMemo<PackBannerScopeValue>(
    () => ({
      register(kind) {
        bump(kind, 1);
        return () => bump(kind, -1);
      },
    }),
    [bump],
  );
  return [counts, scope];
}

export function Screen({ title, back, onBack, children, footer, scroll = true, hideHelpLink, testID }: ScreenProps) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const clerkMode = useSession((s) => s.clerkMode);
  const [shownByScreen, scope] = usePackBannerScope();
  const body = (
    <View style={styles.body}>
      {title ? (
        <Heading level={1} variant="title">
          {title}
        </Heading>
      ) : null}
      <RestartNotice />
      {clerkMode ? null : <PackBanners shownByScreen={shownByScreen} />}
      {children}
    </View>
  );
  return (
    <PackBannerScope.Provider value={scope}>
      <View testID={testID} style={[styles.root, { backgroundColor: colors.background, paddingTop: insets.top }]}>
        {clerkMode ? null : <ScreenHeader back={back} onBack={onBack} hideHelpLink={hideHelpLink} />}
        {scroll ? (
          <ScrollView
            testID="screen-scroll"
            contentContainerStyle={[styles.scroll, { paddingBottom: space.xxxl + (footer ? size.primaryCta : 0) }]}
            keyboardShouldPersistTaps="handled">
            {body}
          </ScrollView>
        ) : (
          <View style={[styles.scroll, styles.flex]}>{body}</View>
        )}
        {footer ? (
          <View
            testID="screen-footer"
            style={[
              styles.footer,
              { borderTopColor: colors.divider, backgroundColor: colors.background, paddingBottom: space.md + insets.bottom },
            ]}>
            {/* At very large text the action bar scrolls inside its half of the screen instead of
                pushing the page content to zero height. */}
            <ScrollView style={styles.footerScroll} bounces={false} keyboardShouldPersistTaps="handled">
              {footer}
            </ScrollView>
          </View>
        ) : null}
      </View>
    </PackBannerScope.Provider>
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
  spacer: {
    flex: 1,
  },
  help: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    paddingHorizontal: space.sm,
    flexShrink: 1,
    maxWidth: '50%',
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
    maxHeight: '50%',
    paddingHorizontal: space.screenGutter,
    paddingTop: space.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  footerScroll: {
    flexGrow: 0,
  },
});
