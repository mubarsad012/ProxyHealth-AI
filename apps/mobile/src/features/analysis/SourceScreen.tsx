// S8 — Original and translation (`/result/[id]/source?block=<span_id>&page=<n>`). Page image with
// tappable highlight boxes (never mirrored), pager, mode toggle, block list with real text in the
// paper's language + the translation, a speaker per block. ≥ 900 px: image beside the list.

import { Image } from 'expo-image';
import { useRef, useState } from 'react';
import { type LayoutChangeEvent, Pressable, ScrollView, StyleSheet, useWindowDimensions, View } from 'react-native';

import type { AnalysisResult } from '@/api/types';
import { Bidi } from '@/design/components/Bidi';
import { Screen } from '@/design/components/Screen';
import { SpeakButton } from '@/design/components/SpeakButton';
import { AppText } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
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
  const { width } = useWindowDimensions();
  const [current, setCurrent] = useState(() => initialSourcePage(a, block, page));
  const [selected, setSelected] = useState<string | null>(block ?? null);
  const [mode, setMode] = useState<SourceMode>('both');
  const [box, setBox] = useState(0);
  const scroll = useRef<ScrollView | null>(null);
  const offsets = useRef<Record<string, number>>({});
  const model = sourcePageModel(a, current);
  const image = pageImageFor(a, pages, current);
  const aspect = image?.width && image?.height ? image.height / image.width : 1.294;
  const wide = width >= 900;
  const selectedRow = model.blocks.find((r) => r.block.id === selected) ?? null;

  const select = (id: string) => {
    setSelected(id);
    const y = offsets.current[id];
    if (y !== undefined) scroll.current?.scrollTo({ y, animated: true });
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
    <View style={[styles.list, wide ? styles.half : null]}>
      {model.partial ? <AppText color="textMuted">{t('warning.translation_partial')}</AppText> : null}
      {model.pageTranslation && mode !== 'original' ? (
        <View style={[styles.block, { borderColor: colors.divider }]}>
          <View style={[styles.row, { flexDirection: dir.row }]}>
            <View style={styles.flex}>
              <AppText lang={a.target_language}>{model.pageTranslation}</AppText>
            </View>
            <SpeakButton text={model.pageTranslation} lang={meta.tag} />
          </View>
        </View>
      ) : null}
      {model.blocks.map((r) => (
        <View
          key={r.block.id}
          testID={`source-block-${r.block.id}`}
          onLayout={(e) => {
            offsets.current[r.block.id] = e.nativeEvent.layout.y;
          }}
          style={[styles.block, { borderColor: r.block.id === selected ? colors.focus : colors.divider }]}>
          {mode !== 'translation' ? (
            <View style={[styles.row, { flexDirection: dir.row }]}>
              <Pressable style={styles.flex} onPress={() => select(r.block.id)} accessibilityLabel={blockLabel(r, current)}>
                <Bidi dir="auto" variant="body">
                  {r.block.text}
                </Bidi>
              </Pressable>
              <SpeakButton text={r.block.text} lang={a.detected_language} />
            </View>
          ) : null}
          {mode !== 'original' && !model.pageTranslation ? (
            <View style={[styles.row, { flexDirection: dir.row }]}>
              <View style={styles.flex}>
                <AppText color={r.translation ? 'text' : 'textMuted'} lang={a.target_language}>
                  {r.translation ?? t('source.not_translated')}
                </AppText>
              </View>
              {r.translation ? <SpeakButton text={r.translation} lang={meta.tag} /> : null}
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
      <ScrollView ref={scroll} contentContainerStyle={[styles.panes, wide ? { flexDirection: dir.row } : null]}>
        {imagePane}
        {listPane}
      </ScrollView>
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
