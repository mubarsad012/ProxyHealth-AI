// S4 — Capture (`/scan/capture`). Native: expo-camera `CameraView` (SDK 57: `facing`,
// `enableTorch`, `ref.takePictureAsync({ quality, exif })`, `useCameraPermissions()`), shutter
// labelled with the page number, torch toggle, "Pick from photos", "Pick a PDF", thumbnail strip
// in document order, Done → S5. Web skips the live camera: the pickers are the first statement
// of each press handler (browser user-gesture rule).

import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import { Image } from 'expo-image';
import { type Href, router } from 'expo-router';
import { useRef, useState } from 'react';
import { AccessibilityInfo, Linking, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Svg, { Path } from 'react-native-svg';

import { useServerConfig } from '@/api/config';
import { Bidi } from '@/design/components/Bidi';
import { Icon } from '@/design/components/Icon';
import { BigButton } from '@/design/components/BigButton';
import { Screen } from '@/design/components/Screen';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { t as tr } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { newPageId } from '@/lib/ids';
import { useOnline } from '@/lib/network';
import { type CapturedPage, useSession } from '@/store/session';

import { usePickImage } from './index';
import { pagesAfterPick, type PickOutcome } from './pageQueue';

function announce(key: string, vars?: Record<string, string | number>) {
  try {
    AccessibilityInfo.announceForAccessibility(tr(key, vars));
  } catch {
    // best-effort
  }
}

/** The torch switch's name ("Light"): the "Too dark. Tap the light." guide line points at it. */
export const TORCH_LABEL_KEY = 'capture.torch';

/** A flashlight (the design icon set has no torch glyph; drawn in the same 24-unit, 2-px style).
 *  Rays show while it is on. Decorative: the switch carries the name and the on/off state. */
function TorchGlyph({ color, on }: { color: string; on: boolean }) {
  const s = { stroke: color, strokeWidth: 2, fill: 'none', strokeLinecap: 'round', strokeLinejoin: 'round' } as const;
  return (
    <Svg width={24} height={24} viewBox="0 0 24 24" accessible={false} aria-hidden importantForAccessibility="no-hide-descendants">
      <Path d="M8 9h8l-1.5 4v7a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1v-7L8 9z" {...s} />
      <Path d="M8 9V7h8v2M12 15v2" {...s} />
      {on ? <Path d="M12 1v2M6.5 3l1.2 1.6M17.5 3l-1.2 1.6" {...s} /> : null}
    </Svg>
  );
}

export function CaptureScreen() {
  const t = useT();
  const { colors } = useTheme();
  const { config } = useServerConfig();
  const { online } = useOnline();
  const limits = config?.limits ?? null;
  const pages = useSession((s) => s.pages);
  const pick = usePickImage();
  const camera = useRef<CameraView | null>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [torch, setTorch] = useState(false);
  // Native has no pixel access: "Too dark" is driven by the torch being switched off again.
  const [torchOffAgain, setTorchOffAgain] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const maxPages = limits?.max_pages ?? 12;
  const atCap = pages.length >= maxPages;

  const apply = (o: PickOutcome) => {
    const s = useSession.getState();
    // A real capture ends any sample session.
    if (s.demoSampleId) s.setDemoSampleId(null);
    s.setPages(o.pages);
    if (o.kind === 'page_cap') setMessage(t('state.page_cap', { max_pages: o.maxPages }));
    else if (o.kind === 'pdf_or_photos') setMessage(t('state.pdf_or_photos'));
    else if (o.kind === 'too_large') setMessage(t('err.payload_too_large', { max_pdf_mb: Math.floor((limits?.max_pdf_bytes ?? 12582912) / 1048576) }));
    else setMessage(null);
    if (o.kind === 'ok' && o.pages.length === 1 && o.pages[0].mimeType === 'application/pdf') router.replace('/scan/review' as Href);
  };

  const fromLibrary = (e?: unknown) => {
    void pick.pickFromLibrary(e).then((picked) => apply(pagesAfterPick(useSession.getState().pages, picked, limits)));
  };
  const fromPdf = (e?: unknown) => {
    void pick.pickPdf(e).then((pdf) => apply(pagesAfterPick(useSession.getState().pages, pdf ? [pdf] : [], limits)));
  };
  const webPhoto = (e?: unknown) => {
    void pick.takePhoto(e).then((picked) => apply(pagesAfterPick(useSession.getState().pages, picked, limits)));
  };

  const shutter = async () => {
    if (!camera.current || busy || atCap) return;
    setBusy(true);
    try {
      const photo = await camera.current.takePictureAsync({ quality: 0.9, exif: false });
      const page: CapturedPage = {
        id: newPageId(),
        uri: photo.uri,
        mimeType: 'image/jpeg',
        width: photo.width,
        height: photo.height,
        rotation: 0,
        masks: [],
        source: 'camera',
      };
      apply(pagesAfterPick(useSession.getState().pages, [page], limits));
      const n = useSession.getState().pages.length;
      void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
      announce('a11y.page_added', { n });
      setMessage(t('capture.guide_added', { n }));
    } catch {
      setMessage(t('err.internal'));
    } finally {
      setBusy(false);
    }
  };

  const done = () => router.replace('/scan/review' as Href);
  const offlineLine = online ? null : <AppText role="status">{t('home.offline_line')}</AppText>;
  const pickers = (
    <View style={styles.stack}>
      <BigButton label={t('capture.pick_from_photos')} icon="image" variant="secondary" size={56} onPress={(e) => fromLibrary(e)} disabled={atCap} />
      <BigButton label={t('capture.pick_pdf')} icon="papers" variant="secondary" size={56} onPress={(e) => fromPdf(e)} disabled={pages.length > 0} />
    </View>
  );
  const strip = pages.length ? (
    <ScrollView horizontal style={styles.strip} contentContainerStyle={styles.stripInner}>
      {pages.map((p, i) => (
        <View key={p.id} style={[styles.thumb, { borderColor: colors.border }]}>
          {p.mimeType === 'application/pdf' ? (
            <Icon name="papers" color={colors.primary} size={40} />
          ) : (
            <Image source={{ uri: p.uri }} contentFit="cover" style={styles.thumbImg} accessibilityLabel={t('a11y.page_added', { n: i + 1 })} />
          )}
          <Bidi dir="ltr" variant="caption" weight="bold">
            {String(i + 1)}
          </Bidi>
        </View>
      ))}
    </ScrollView>
  ) : null;
  const footer = pages.length ? <BigButton label={t('capture.done')} icon="check" variant="primary" size={72} onPress={done} /> : undefined;

  if (Platform.OS === 'web') {
    return (
      <Screen back footer={footer} testID="capture-screen">
        {offlineLine}
        <BigButton label={t('btn.scan')} icon="camera" variant="primary" size={72} onPress={(e) => webPhoto(e)} disabled={atCap} />
        {pickers}
        {message ? <AppText role="status">{message}</AppText> : null}
        {strip}
      </Screen>
    );
  }

  if (!permission || (!permission.granted && permission.canAskAgain)) {
    return (
      <Screen back testID="capture-screen">
        <AppText variant="bodyLarge">{t('capture.permission_rationale')}</AppText>
        <BigButton label={t('btn.allow_camera')} icon="camera" variant="primary" size={72} onPress={() => void requestPermission()} />
        {pickers}
      </Screen>
    );
  }

  if (!permission.granted) {
    return (
      <Screen back testID="capture-screen">
        <AppText variant="bodyLarge">{t('state.camera_denied')}</AppText>
        <BigButton label={t('btn.open_settings')} icon="settings" variant="primary" size={72} onPress={() => void Linking.openSettings()} />
        <BigButton label={t('btn.pick_instead')} icon="image" variant="secondary" size={56} onPress={(e) => fromLibrary(e)} />
        {pickers}
      </Screen>
    );
  }

  return (
    <Screen back footer={footer} testID="capture-screen">
      {offlineLine}
      <AppText role="status" weight="bold">
        {message ?? (atCap ? t('state.page_cap', { max_pages: maxPages }) : torchOffAgain ? t('capture.guide_dark') : t('capture.guide_fit'))}
      </AppText>
      <View style={[styles.cameraWrap, { borderColor: colors.border }]}>
        <CameraView ref={camera} style={StyleSheet.absoluteFill} facing="back" enableTorch={torch} />
        <View pointerEvents="none" style={[styles.guide, { borderColor: colors.onPrimary }]} />
      </View>
      <View style={styles.controls}>
        <Pressable
          role="switch"
          testID="capture-torch"
          accessibilityLabel={t(TORCH_LABEL_KEY)}
          accessibilityState={{ checked: torch }}
          aria-checked={torch}
          onPress={() => {
            if (torch) setTorchOffAgain(true);
            setTorch(!torch);
          }}
          style={[styles.torch, { borderColor: colors.border, backgroundColor: torch ? colors.secondary : colors.surface }]}>
          <TorchGlyph color={colors.text} on={torch} />
        </Pressable>
        <Pressable
          role="button"
          testID="capture-shutter"
          accessibilityLabel={t('capture.shutter_label', { n: pages.length + 1 })}
          disabled={busy || atCap}
          onPress={() => void shutter()}
          style={[styles.shutter, { borderColor: colors.primary, opacity: busy || atCap ? 0.5 : 1 }]}>
          <View style={[styles.shutterInner, { backgroundColor: colors.primary }]} />
        </Pressable>
      </View>
      {pickers}
      {strip}
    </Screen>
  );
}

const styles = StyleSheet.create({
  stack: { gap: space.sm },
  cameraWrap: { width: '100%', aspectRatio: 0.75, borderWidth: 1, borderRadius: radius.lg, overflow: 'hidden' },
  guide: { position: 'absolute', left: '8%', right: '8%', top: '6%', bottom: '6%', borderWidth: 2, borderStyle: 'dashed', borderRadius: radius.sm },
  controls: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: space.xl },
  torch: { width: 56, height: 56, borderRadius: 28, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  shutter: { width: 80, height: 80, borderRadius: 40, borderWidth: 4, alignItems: 'center', justifyContent: 'center' },
  shutterInner: { width: 60, height: 60, borderRadius: 30 },
  strip: { flexGrow: 0 },
  stripInner: { gap: space.sm, flexDirection: 'row' },
  thumb: { width: 72, alignItems: 'center', gap: space.xxs, borderWidth: 1, borderRadius: radius.sm, padding: space.xxs },
  thumbImg: { width: 64, height: 84 },
});
