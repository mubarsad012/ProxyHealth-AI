// S8 — Original and translation (`/result/[id]/source?block=<span_id>&page=<n>`). Page image with
// tappable highlight boxes (never mirrored), pager, mode toggle, block list with real text in the
// paper's language + the translation, a speaker per block. ≥ 900 px: image beside the list.

import { Image } from 'expo-image';
import { useEffect, useRef, useState } from 'react';
import { type LayoutChangeEvent, Pressable, ScrollView, StyleSheet, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { AnalysisResult } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { Screen } from '@/design/components/Screen';
import { SpeakButton } from '@/design/components/SpeakButton';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { useTtsFallbackNotice } from '@/features/speech';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { usePackMeta, useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { pageImageFor } from './pageImages';
import { blockLabel, initialSourcePage, type SourceMode, sourcePageModel, sourcePages } from './sourceModel';

export interface SourceScreenProps {
  analysis: AnalysisResult;
  pages: readonly CapturedPage[];
  block?: string | null;
  page?: string | null;
  imagesKept?: boolean;
}

export function SourceScreen({ analysis: a, pages, block, page, imagesKept = true }: SourceScreenProps) {
  const t = useT();
  const meta = usePackMeta();
  const { colors } = useTheme();
  const dir = useDirection();
  const { width, height } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  // `Screen scroll={false}` does not bound its body's height, so the pane below the toolbars gets
  // an explicit height (window minus its measured top) — otherwise the inner ScrollView grows to
  // its content, the page scrolls instead (web) or is clipped (native), and `?block=` cannot scroll.
  const paneRef = useRef<View | null>(null);
  const [paneTop, setPaneTop] = useState<number | null>(null);
  const measurePane = () => paneRef.current?.measureInWindow((_x, y) => setPaneTop(Math.max(0, y)));
  const paneHeight = paneTop === null ? undefined : Math.max(280, height - paneTop - insets.bottom);
  // Also measure after mount / window resize (onLayout alone can be late on web).
  useEffect(() => {
    const id = setTimeout(() => paneRef.current?.measureInWindow((_x, y) => setPaneTop(Math.max(0, y))), 0);
    return () => clearTimeout(id);
  }, [width, height]);
  const [current, setCurrent] = useState(() => initialSourcePage(a, block, page));
  const [selected, setSelected] = useState<string | null>(block ?? null);
  const [mode, setMode] = useState<SourceMode>('both');
  const [box, setBox] = useState(0);
  const scroll = useRef<ScrollView | null>(null);
  // Block offsets are relative to the list pane; the pane's own offset is added when scrolling
  // (phone layout puts the page image above the list).
  const offsets = useRef<Record<string, number>>({});
  const listY = useRef<number | null>(null);
  const initialScrolled = useRef(!block);
  // Honest TTS line (D-26) per speaker language: the paper's own words are read in
  // `detected_language`, translations in the UI pack. Shown above the panes, so it stays visible.
  const originalVoice = useTtsFallbackNotice(a.detected_language);
  const translationVoice = useTtsFallbackNotice(meta.tag);
  const voiceNotices = [originalVoice.notice, translationVoice.notice].filter(
    (n, i, all): n is string => Boolean(n) && all.indexOf(n) === i,
  );
  const model = sourcePageModel(a, current);
  const image = pageImageFor(a, pages, current);
  const aspect = image?.width && image?.height ? image.height / image.width : 1.294;
  const wide = width >= 900;
  const selectedRow = model.blocks.find((r) => r.block.id === selected) ?? null;

  const scrollToBlock = (id: string, animated: boolean): boolean => {
    const y = offsets.current[id];
    if (y === undefined || listY.current === null) return false;
    scroll.current?.scrollTo({ y: Math.max(0, listY.current + y - space.md), animated });
    return true;
  };

  /** `?block=` opens scrolled to that block once both layouts are known. */
  const maybeInitialScroll = () => {
    if (initialScrolled.current || !block) return;
    if (scrollToBlock(block, false)) initialScrolled.current = true;
  };

  const select = (id: string) => {
    setSelected(id);
    scrollToBlock(id, true);
  };

  const imagePane = (
    <View style={[styles.imagePane, wide ? styles.half : null]}>
      {image ? (
        <View
          onLayout={(e: LayoutChangeEvent) => setBox(e.nativeEvent.layout.width)}
          style={[styles.pageImage, { height: box ? box * aspect : 320, borderColor: colors.divider }]}>
          <Image source={{ uri: image.uri }} contentFit="fill" style={StyleSheet.absoluteFill} accessibilityLabel={a.summary.title} />
          {model.blocks.map((r) =>
            r.block.bbox && box ? (
              <Pressable
                key={r.block.id}
                role="button"
                accessibilityLabel={blockLabel(r, current)}
                onPress={() => select(r.block.id)}
                style={[
                  styles.hit,
                  {
                    left: r.block.bbox[0] * box,
                    top: r.block.bbox[1] * box * aspect,
                    width: (r.block.bbox[2] - r.block.bbox[0]) * box,
                    height: (r.block.bbox[3] - r.block.bbox[1]) * box * aspect,
                    borderColor: r.block.id === selected ? colors.focus : 'transparent',
                    backgroundColor: r.block.id === selected ? 'rgba(255, 214, 0, 0.25)' : 'transparent',
                  },
                ]}
              />
            ) : null,
          )}
        </View>
      ) : (
        <AppText color="textMuted">{imagesKept ? (selectedRow ? selectedRow.block.text : '') : t('source.no_image')}</AppText>
      )}
      {selectedRow && !selectedRow.block.bbox ? (
        <AppText color="textMuted">{t('source.no_box', { quote: selectedRow.block.text })}</AppText>
      ) : null}
    </View>
  );

  const listPane = (
    <View
      onLayout={(e: LayoutChangeEvent) => {
        listY.current = wide ? 0 : e.nativeEvent.layout.y;
        maybeInitialScroll();
      }}
      style={[styles.list, wide ? styles.half : null]}>
      {model.partial ? <AppText color="textMuted">{t('warning.translation_partial')}</AppText> : null}
      {model.pageTranslation && mode !== 'original' ? (
        <View style={[styles.block, { borderColor: colors.divider }]}>
          <View style={[styles.row, { flexDirection: dir.row }]}>
            <View style={styles.flex}>
              <AppText lang={a.target_language}>{model.pageTranslation}</AppText>
            </View>
            <SpeakButton text={model.pageTranslation} lang={meta.tag} onResolved={translationVoice.onResolved} />
          </View>
        </View>
      ) : null}
      {model.blocks.map((r) => (
        <View
          key={r.block.id}
          testID={`source-block-${r.block.id}`}
          onLayout={(e) => {
            offsets.current[r.block.id] = e.nativeEvent.layout.y;
            if (r.block.id === block) maybeInitialScroll();
          }}
          style={[styles.block, { borderColor: r.block.id === selected ? colors.focus : colors.divider }]}>
          {mode !== 'translation' ? (
            <View style={[styles.row, { flexDirection: dir.row }]}>
              <Pressable style={styles.flex} onPress={() => select(r.block.id)} accessibilityLabel={blockLabel(r, current)}>
                <Bidi dir="auto" variant="body">
                  {r.block.text}
                </Bidi>
              </Pressable>
              <SpeakButton text={r.block.text} lang={a.detected_language} onResolved={originalVoice.onResolved} />
            </View>
          ) : null}
          {mode !== 'original' && !model.pageTranslation ? (
            <View style={[styles.row, { flexDirection: dir.row }]}>
              <View style={styles.flex}>
                <AppText color={r.translation ? 'text' : 'textMuted'} lang={a.target_language}>
                  {r.translation ?? t('source.not_translated')}
                </AppText>
              </View>
              {r.translation ? <SpeakButton text={r.translation} lang={meta.tag} onResolved={translationVoice.onResolved} /> : null}
            </View>
          ) : null}
          <View style={[styles.badges, { flexDirection: dir.row }]}>
            {r.block.is_unclear ? <AppText variant="caption" color="warning">{t('source.unclear')}</AppText> : null}
            {r.block.is_handwriting ? <AppText variant="caption" color="textMuted">{t('source.handwriting')}</AppText> : null}
          </View>
        </View>
      ))}
    </View>
  );

  const modes: SourceMode[] = ['original', 'both', 'translation'];
  return (
    <Screen back scroll={false} testID="source-screen">
      <View style={[styles.toolbar, { flexDirection: dir.row }]}>
        {modes.map((m) => (
          <Pressable
            key={m}
            role="button"
            accessibilityState={{ selected: mode === m }}
            accessibilityLabel={t(`source.mode_${m}`)}
            onPress={() => setMode(m)}
            style={[styles.toggle, { borderColor: colors.primary, backgroundColor: mode === m ? colors.primary : colors.surface }]}>
            <AppText variant="caption" weight="bold" colorValue={mode === m ? colors.onPrimary : colors.primary}>
              {t(`source.mode_${m}`)}
            </AppText>
          </Pressable>
        ))}
      </View>
      {sourcePages(a).length > 1 ? (
        <View style={[styles.toolbar, { flexDirection: dir.row }]}>
          {sourcePages(a).map((n) => (
            <Pressable
              key={n}
              role="button"
              accessibilityState={{ selected: n === current }}
              accessibilityLabel={t('card.found_on_page', { page: n })}
              onPress={() => setCurrent(n)}
              style={[styles.pageBtn, { borderColor: colors.border, backgroundColor: n === current ? colors.secondary : colors.surface }]}>
              <Bidi dir="ltr" variant="body" weight="bold">
                {String(n)}
              </Bidi>
            </Pressable>
          ))}
        </View>
      ) : null}
      {voiceNotices.map((n) => (
        <AppText key={n} variant="caption" color="textMuted" role="status" testID="tts-fallback-notice">
          {n}
        </AppText>
      ))}
      <View ref={paneRef} onLayout={measurePane} style={paneHeight ? { height: paneHeight } : null} testID="source-panes">
        <ScrollView ref={scroll} style={styles.flex} contentContainerStyle={[styles.panes, wide ? { flexDirection: dir.row } : null]}>
          {imagePane}
          {listPane}
        </ScrollView>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  toolbar: { flexWrap: 'wrap', gap: space.sm },
  toggle: { minHeight: size.minTouch, justifyContent: 'center', borderWidth: 2, borderRadius: radius.pill, paddingHorizontal: space.md },
  pageBtn: { minWidth: size.minTouch, minHeight: size.minTouch, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderRadius: radius.sm },
  panes: { gap: space.lg, paddingBottom: space.xxxl },
  half: { flex: 1 },
  imagePane: { gap: space.sm },
  pageImage: { width: '100%', borderWidth: 1, overflow: 'hidden', direction: 'ltr' },
  hit: { position: 'absolute', borderWidth: 2, borderRadius: radius.sm },
  list: { gap: space.sm },
  block: { borderWidth: 1, borderRadius: radius.md, padding: space.md, gap: space.xs },
  row: { alignItems: 'center', gap: space.sm },
  flex: { flex: 1 },
  badges: { gap: space.sm },
});
