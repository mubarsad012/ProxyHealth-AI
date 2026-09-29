// S5 — Review pages (`/scan/review`, `?sample=<fixture_id>` from the sample picker). Fix pages
// (take again / turn / remove), hide parts, then "Read this paper" → S6. PDFs show a file card.
// Offline: the primary becomes "Save to read later" and the scan is queued in the session.

import { Image } from 'expo-image';
import { type Href, router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, View } from 'react-native';

import { useApi, useServerConfig } from '@/api/config';
import { Banner } from '@/design/components/Banner';
import { Bidi } from '@/design/components/Bidi';
import { BigButton } from '@/design/components/BigButton';
import { Icon } from '@/design/components/Icon';
import { Screen } from '@/design/components/Screen';
import { EmptyState } from '@/design/components/States';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { useI18n } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import { newId } from '@/lib/ids';
import { useOnline } from '@/lib/network';
import { pdfSizeMb } from '@/lib/pdf';
import { type CapturedPage, useSession } from '@/store/session';

import { turnPage } from './compress';
import { usePickImage } from './index';
import { MaskEditor } from './MaskEditor';
import { pagesAfterPick, type PickOutcome } from './pageQueue';
import { forgetWebFile } from './pick';
import { samplePages } from './samples';

function PageCard({ page, n, sample, onRetake, onTurn, onRemove, onHide }: {
  page: CapturedPage;
  n: number;
  sample: boolean;
  onRetake(e?: unknown): void;
  onTurn(): void;
  onRemove(): void;
  onHide(): void;
}) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const aspect = page.width && page.height ? page.width / page.height : 0.77;
  return (
    <View testID={`review-page-${n}`} style={[styles.card, { borderColor: colors.divider, backgroundColor: colors.surface }]}>
      <View style={styles.imageWrap}>
        <Image source={{ uri: page.uri }} contentFit="contain" style={[styles.image, { aspectRatio: aspect }]} accessibilityLabel={`${n}`} />
        {page.masks.map((m, i) => (
          <View
            key={i}
            pointerEvents="none"
            style={[styles.mask, { left: `${m.x0 * 100}%`, top: `${m.y0 * 100}%`, width: `${(m.x1 - m.x0) * 100}%`, height: `${(m.y1 - m.y0) * 100}%` }]}
          />
        ))}
      </View>
      <AppText weight="bold" align="center">
        <Bidi dir="ltr">{String(n)}</Bidi>
      </AppText>
      {sample ? null : (
        <View style={[styles.actions, { flexDirection: dir.row }]}>
          <SmallAction label={t('review.retake')} icon="camera" onPress={onRetake} />
          <SmallAction label={t('review.rotate')} icon="refresh" onPress={onTurn} />
          <SmallAction label={t('review.hide_parts')} icon="lock" onPress={onHide} />
          <SmallAction label={t('review.remove')} icon="close" onPress={onRemove} danger />
        </View>
      )}
    </View>
  );
}

function SmallAction({ label, icon, onPress, danger }: { label: string; icon: 'camera' | 'refresh' | 'lock' | 'close'; onPress(e?: unknown): void; danger?: boolean }) {
  const { colors } = useTheme();
  const dir = useDirection();
  const color = danger ? colors.danger : colors.primary;
  return (
    <Pressable
      role="button"
      accessibilityLabel={label}
      hitSlop={size.hitSlop}
      onPress={(e) => onPress(e)}
      style={[styles.small, { borderColor: color, flexDirection: dir.row }]}>
      <Icon name={icon} size={18} color={color} />
      <AppText variant="caption" weight="bold" colorValue={color}>
        {label}
      </AppText>
    </Pressable>
  );
}

export function ReviewScreen() {
  const t = useT();
  const dir = useDirection();
  const client = useApi();
  const { config } = useServerConfig();
  const { online } = useOnline();
  const params = useLocalSearchParams<{ sample?: string }>();
  const pages = useSession((s) => s.pages);
  const demoSampleId = useSession((s) => s.demoSampleId);
  const pick = usePickImage();
  const [editing, setEditing] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const limits = config?.limits ?? null;
  const sampleParam = typeof params.sample === 'string' && params.sample ? params.sample : null;

  useEffect(() => {
    if (!sampleParam) return;
    const s = useSession.getState();
    if (s.demoSampleId === sampleParam && s.pages.length) return;
    s.setPages(samplePages(client, sampleParam));
    s.setDemoSampleId(sampleParam);
  }, [client, sampleParam]);

  const sample = Boolean(demoSampleId);
  const isPdf = pages.length === 1 && pages[0].mimeType === 'application/pdf';

  const applyOutcome = (o: PickOutcome) => {
    useSession.getState().setPages(o.pages);
    if (o.kind === 'page_cap') setMessage(t('state.page_cap', { max_pages: o.maxPages }));
    else if (o.kind === 'pdf_or_photos') setMessage(t('state.pdf_or_photos'));
    else if (o.kind === 'too_large') setMessage(t('err.payload_too_large', { max_pdf_mb: Math.floor((limits?.max_pdf_bytes ?? 12582912) / 1048576) }));
    else setMessage(null);
  };

  const addPages = (e?: unknown) => {
    if (Platform.OS === 'web') {
      void pick.pickFromLibrary(e).then((picked) => applyOutcome(pagesAfterPick(useSession.getState().pages, picked, limits)));
      return;
    }
    router.push('/scan/capture' as Href);
  };

  const retake = (page: CapturedPage, e?: unknown) => {
    if (Platform.OS === 'web') {
      void pick.takePhoto(e).then((picked) => {
        if (!picked.length) return;
        const s = useSession.getState();
        forgetWebFile(page.id);
        s.setPages(s.pages.map((p) => (p.id === page.id ? picked[0] : p)));
      });
      return;
    }
    useSession.getState().removePage(page.id);
    router.push('/scan/capture' as Href);
  };

  const turn = (page: CapturedPage) => {
    void turnPage(page)
      .then((next) => useSession.getState().updatePage(page.id, next))
      .catch(() => setMessage(t('err.internal')));
  };

  const remove = (page: CapturedPage) => {
    forgetWebFile(page.id);
    useSession.getState().removePage(page.id);
  };

  const readLater = () => {
    const s = useSession.getState();
    s.enqueueOfflineScan({ id: newId(), pages: s.pages, targetLanguage: useI18n.getState().tag, memberId: null, queuedAt: new Date().toISOString() });
    setMessage(t('capture.offline_queue'));
  };

  if (!pages.length && !sampleParam) {
    return (
      <Screen back testID="review-screen">
        <EmptyState text={t('home.scan_hint')} icon="camera" actionLabel={t('btn.scan')} onAction={() => addPages()} />
      </Screen>
    );
  }

  const editingPage = pages.find((p) => p.id === editing) ?? null;
  const footer = online ? (
    <BigButton
      testID="review-read"
      label={t('review.read_cta')}
      icon="check"
      variant="primary"
      size={72}
      accessibilityHint={t('review.read_hint', { n: pages.length })}
      disabled={!pages.length}
      onPress={() => router.push('/scan/reading' as Href)}
    />
  ) : (
    <View style={styles.footer}>
      <BigButton label={t('review.read_later_cta')} icon="offline" variant="primary" size={72} onPress={readLater} />
      <BigButton label={t('review.wait_for_internet')} variant="secondary" size={56} onPress={readLater} />
    </View>
  );

  return (
    <Screen back footer={footer} testID="review-screen">
      {sample ? <Banner kind="demo" text={t('banner.demo_sample')} /> : null}
      {message ? (
        <AppText role="status" weight="bold">
          {message}
        </AppText>
      ) : null}
      {isPdf ? (
        <PdfCard page={pages[0]} onRemove={() => remove(pages[0])} />
      ) : (
        <View style={[styles.grid, { flexDirection: dir.row }]}>
          {pages.map((p, i) => (
            <View key={p.id} style={styles.cell}>
              <PageCard
                page={p}
                n={i + 1}
                sample={sample}
                onRetake={(e) => retake(p, e)}
                onTurn={() => turn(p)}
                onRemove={() => remove(p)}
                onHide={() => setEditing(p.id)}
              />
            </View>
          ))}
        </View>
      )}
      {!sample && !isPdf ? (
        <>
          <AppText color="textMuted">{t('review.hide_tip')}</AppText>
          <BigButton label={t('capture.add_page')} icon="camera" variant="secondary" size={56} onPress={(e) => addPages(e)} />
        </>
      ) : null}
      {editingPage ? (
        <MaskEditor
          page={editingPage}
          pageNumber={pages.indexOf(editingPage) + 1}
          visible
          onChange={(masks) => useSession.getState().updatePage(editingPage.id, { masks })}
          onClose={() => setEditing(null)}
        />
      ) : null}
    </Screen>
  );
}

function PdfCard({ page, onRemove }: { page: CapturedPage; onRemove(): void }) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  return (
    <View testID="review-pdf" style={[styles.card, { borderColor: colors.divider, backgroundColor: colors.surface }]}>
      <View style={[styles.pdfRow, { flexDirection: dir.row }]}>
        <Icon name="papers" size={40} color={colors.primary} />
        <View style={styles.flex}>
          <AppText weight="bold">{t('review.pdf_summary', { size: pdfSizeMb(page.byteLength ?? 0) })}</AppText>
          {page.fileName ? <Bidi dir="auto" variant="caption">{page.fileName}</Bidi> : null}
        </View>
      </View>
      <SmallAction label={t('review.remove')} icon="close" onPress={onRemove} danger />
    </View>
  );
}

const styles = StyleSheet.create({
  grid: { flexWrap: 'wrap', gap: space.md },
  cell: { flexGrow: 1, flexBasis: 160, maxWidth: '100%' },
  card: { borderWidth: 1, borderRadius: radius.lg, padding: space.md, gap: space.sm },
  imageWrap: { width: '100%', position: 'relative', direction: 'ltr' },
  image: { width: '100%', borderRadius: radius.sm },
  mask: { position: 'absolute', backgroundColor: '#000000' },
  actions: { flexWrap: 'wrap', gap: space.xs },
  small: {
    minHeight: size.minTouch,
    alignItems: 'center',
    gap: space.xs,
    borderWidth: 2,
    borderRadius: radius.pill,
    paddingHorizontal: space.sm,
  },
  footer: { gap: space.sm },
  pdfRow: { alignItems: 'center', gap: space.md },
  flex: { flex: 1 },
});
