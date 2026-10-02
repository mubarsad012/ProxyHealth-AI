// S8 — Original and translation (`/result/[id]/source?block=<span_id>&page=<n>`). Page image with
// tappable highlight boxes (never mirrored), pager, mode toggle, block list with real text in the
// paper's language + the translation, a speaker per block. ≥ 900 px: image beside the list.

import { Image } from 'expo-image';
import { useEffect, useRef, useState } from 'react';
import {
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  useWindowDimensions,
  View,
} from 'react-native';
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

import { paperLangProps, SourceText } from './cards/shared';
import { pageImageFor } from './pageImages';
import { blockLabel, initialSourcePage, type SourceMode, sourcePageModel, sourcePages } from './sourceModel';

export interface SourceScreenProps {
  analysis: AnalysisResult;
  pages: readonly CapturedPage[];
  block?: string | null;
  page?: string | null;
  imagesKept?: boolean;
}

// ---------------------------------------------------------------------------------------------
// `?block=` initial scroll. On web, onLayout comes from a ResizeObserver: it fires only when a
// view's *size* changes (never for a pure move), and the pane is unbounded — so not scrollable —
// until its top has been measured. The first scroll therefore waits until the pane has its height
// and the ScrollView reports that height, measures the block live (cached onLayout positions go
// stale on web), and checks the offset really moved, retrying on the next frame. It keeps the
// block in place through late layout changes for a short settle window, and stops for good the
// moment the user touches, drags, taps a block, changes page or scrolls on their own.

/** Pixel slack when comparing scroll offsets (sub-pixel rounding on web). */
export const SCROLL_TOLERANCE = 2;
/** After the scroll has landed, keep it on the block through layout changes for this long. */
export const SETTLE_MS = 1000;
/** Hard stop for the whole initial scroll, counted from `start()`. */
export const INITIAL_SCROLL_MAX_MS = 6000;
/** Scroll commands issued without the offset confirming before giving up. */
export const INITIAL_SCROLL_MAX_TRIES = 30;

export interface ScrollMetrics {
  /** The pane's explicit height; null while its top is unmeasured (pane unbounded). */
  paneHeight: number | null;
  /** Visible height of the ScrollView, from its onLayout. */
  viewport: number | null;
  /** Height of the scroll content, from onContentSizeChange. */
  content: number | null;
}

/** True once the pane is bounded and the ScrollView's viewport already reflects that height. */
export function scrollMetricsReady(m: ScrollMetrics): boolean {
  if (m.paneHeight === null || m.viewport === null || m.content === null) return false;
  return m.viewport > 0 && m.viewport <= m.paneHeight + SCROLL_TOLERANCE;
}

/** Offset that puts a block `gap` below the pane's top, clamped to what can scroll; null while
 *  the block is unmeasured or the metrics are not ready (try again on a later layout / frame). */
export function blockScrollTarget(blockY: number | null, m: ScrollMetrics, gap: number = space.md): number | null {
  if (blockY === null || !scrollMetricsReady(m)) return null;
  const max = Math.max(0, (m.content ?? 0) - (m.viewport ?? 0));
  return Math.min(max, Math.max(0, blockY - gap));
}

export interface InitialScrollDeps {
  /** The block's top relative to the scroll content, measured live (async on web); null = absent. */
  measure(done: (y: number | null) => void): void;
  metrics(): ScrollMetrics;
  scrollTo(y: number): void;
  /** Run `cb` on the next frame; returns a cancel function. */
  frame(cb: () => void): () => void;
  timer(cb: () => void, ms: number): () => void;
  now(): number;
}

export type InitialScrollState = 'idle' | 'pending' | 'settling' | 'done';

/** Drives the `?block=` initial scroll (pure: platform calls come in through `deps`). */
export class InitialBlockScroll {
  state: InitialScrollState = 'idle';
  private readonly deps: InitialScrollDeps;
  private offset = 0;
  private issued: number | null = null;
  private tries = 0;
  private startedAt = 0;
  private cancelFrame: (() => void) | null = null;
  private cancelTimer: (() => void) | null = null;

  constructor(deps: InitialScrollDeps) {
    this.deps = deps;
  }

  get active(): boolean {
    return this.state === 'pending' || this.state === 'settling';
  }

  /** Start (or restart, e.g. after a StrictMode effect replay) waiting for the layout. */
  start(): void {
    this.clear();
    this.state = 'pending';
    this.issued = null;
    this.tries = 0;
    this.startedAt = this.deps.now();
    this.kick();
  }

  /** A layout that may bound the pane or move the block changed: try again on the next frame. */
  kick(): void {
    if (!this.active || this.cancelFrame) return;
    this.cancelFrame = this.deps.frame(() => {
      this.cancelFrame = null;
      this.attempt();
    });
  }

  /** onScroll: remember the offset; movement we did not ask for means the user took over. */
  onScroll(y: number, maxY?: number): void {
    this.offset = y;
    if (!this.active) return;
    const expected = this.issued === null ? 0 : Math.min(this.issued, maxY ?? this.issued);
    if (Math.abs(y - expected) > SCROLL_TOLERANCE) this.stop();
  }

  /** The user touched, dragged, tapped a block or changed page: never scroll on our own again. */
  stop(): void {
    this.state = 'done';
    this.clear();
  }

  private clear(): void {
    this.cancelFrame?.();
    this.cancelFrame = null;
    this.cancelTimer?.();
    this.cancelTimer = null;
  }

  private attempt(): void {
    if (!this.active) return;
    if (this.deps.now() - this.startedAt > INITIAL_SCROLL_MAX_MS) return this.stop();
    // Pane still unbounded (or its viewport not re-measured yet): its next layout kicks again.
    if (!scrollMetricsReady(this.deps.metrics())) return;
    this.deps.measure((y) => this.apply(y));
  }

  private apply(y: number | null): void {
    if (!this.active) return;
    const target = blockScrollTarget(y, this.deps.metrics());
    if (target === null) return;
    if (Math.abs(this.offset - target) <= SCROLL_TOLERANCE) {
      // Landed (or nothing to scroll): hold it through late layout changes, then let go.
      this.state = 'settling';
      this.cancelTimer?.();
      this.cancelTimer = this.deps.timer(() => this.stop(), SETTLE_MS);
      return;
    }
    this.tries += 1;
    if (this.tries > INITIAL_SCROLL_MAX_TRIES) return this.stop();
    this.state = 'pending';
    this.issued = target;
    this.deps.scrollTo(target);
    this.kick(); // verify on the next frame; re-issue if the offset did not move
  }
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
  // Blocks are measured live against the scroll content when scrolling to them (never cached
  // onLayout positions: on web those miss pure moves, e.g. the page image growing above the list).
  const contentRef = useRef<View | null>(null);
  const blockRefs = useRef<Record<string, View | null>>({});
  const metrics = useRef<ScrollMetrics>({ paneHeight: null, viewport: null, content: null });
  const scroller = useRef<InitialBlockScroll | null>(null);

  /** The block's top relative to the scroll content, or null when it is not rendered. */
  const measureBlock = (id: string, done: (y: number | null) => void) => {
    const node = blockRefs.current[id];
    const content = contentRef.current;
    if (!node || !content) {
      done(null);
      return;
    }
    node.measureLayout(content, (_x, y) => done(y), () => done(null));
  };

  // `?block=`: scroll to that block once the pane is bounded and the block is measured.
  useEffect(() => {
    if (!block) return;
    const s = new InitialBlockScroll({
      measure: (done) => measureBlock(block, done),
      metrics: () => metrics.current,
      scrollTo: (y) => scroll.current?.scrollTo({ y, animated: false }),
      frame: (cb) => {
        const id = requestAnimationFrame(cb);
        return () => cancelAnimationFrame(id);
      },
      timer: (cb, ms) => {
        const id = setTimeout(cb, ms);
        return () => clearTimeout(id);
      },
      now: () => Date.now(),
    });
    scroller.current = s;
    s.start();
    return () => {
      s.stop();
      if (scroller.current === s) scroller.current = null;
    };
  }, [block]);

  useEffect(() => {
    metrics.current.paneHeight = paneHeight ?? null;
    scroller.current?.kick();
  }, [paneHeight]);

  // Honest TTS line (D-26) per speaker language: the paper's own words are read in
  // `detected_language`, translations in the language they are written in — the S5 output
  // language (`target_language`), which can differ from the UI pack. Shown above the panes.
  const translationLang = a.target_language || meta.tag;
  const originalVoice = useTtsFallbackNotice(a.detected_language);
  const translationVoice = useTtsFallbackNotice(translationLang);
  const voiceNotices = [originalVoice.notice, translationVoice.notice].filter(
    (n, i, all): n is string => Boolean(n) && all.indexOf(n) === i,
  );
  const model = sourcePageModel(a, current);
  const image = pageImageFor(a, pages, current);
  const aspect = image?.width && image?.height ? image.height / image.width : 1.294;
  const wide = width >= 900;
  const selectedRow = model.blocks.find((r) => r.block.id === selected) ?? null;

  const select = (id: string) => {
    scroller.current?.stop();
    setSelected(id);
    measureBlock(id, (y) => {
      if (y !== null) scroll.current?.scrollTo({ y: Math.max(0, y - space.md), animated: true });
    });
  };

  const imagePane = (
    <View style={[styles.imagePane, wide ? styles.half : null]}>
      {image ? (
        <View
          onLayout={(e: LayoutChangeEvent) => setBox(e.nativeEvent.layout.width)}
          style={[styles.pageImage, { height: box ? box * aspect : 320, borderColor: colors.divider }]}>
          <Image source={{ uri: image.uri }} cachePolicy="memory" contentFit="fill" style={StyleSheet.absoluteFill} accessibilityLabel={a.summary.title} />
          {model.blocks.map((r) =>
            r.block.bbox && box ? (
              <Pressable
                key={r.block.id}
                role="button"
                accessibilityLabel={blockLabel(r, current)}
                {...paperLangProps(a.detected_language, dir.dir)}
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
            <SpeakButton text={model.pageTranslation} lang={translationLang} onResolved={translationVoice.onResolved} />
          </View>
        </View>
      ) : null}
      {model.blocks.map((r) => (
        <View
          key={r.block.id}
          ref={(node) => {
            blockRefs.current[r.block.id] = node;
          }}
          collapsable={false}
          testID={`source-block-${r.block.id}`}
          // Native reports moves here too; the target block's layout is worth another try.
          onLayout={r.block.id === block ? () => scroller.current?.kick() : undefined}
          style={[styles.block, { borderColor: r.block.id === selected ? colors.focus : colors.divider }]}>
          {mode !== 'translation' ? (
            <View style={[styles.row, { flexDirection: dir.row }]}>
              <Pressable
                style={styles.flex}
                onPress={() => select(r.block.id)}
                accessibilityLabel={blockLabel(r, current)}
                {...paperLangProps(a.detected_language, dir.dir)}>
                <SourceText lang={a.detected_language}>{r.block.text}</SourceText>
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
              {r.translation ? <SpeakButton text={r.translation} lang={translationLang} onResolved={translationVoice.onResolved} /> : null}
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
              onPress={() => {
                scroller.current?.stop();
                setCurrent(n);
              }}
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
      <View
        ref={paneRef}
        onLayout={() => {
          measurePane();
          scroller.current?.kick();
        }}
        style={paneHeight ? { height: paneHeight } : null}
        testID="source-panes">
        <ScrollView
          ref={scroll}
          testID="source-scroll"
          style={styles.flex}
          scrollEventThrottle={16}
          onLayout={(e: LayoutChangeEvent) => {
            metrics.current.viewport = e.nativeEvent.layout.height;
            scroller.current?.kick();
          }}
          onContentSizeChange={(_w, h) => {
            metrics.current.content = h;
            scroller.current?.kick();
          }}
          onScroll={(e: NativeSyntheticEvent<NativeScrollEvent>) => {
            const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
            let maxY: number | undefined;
            if (contentSize?.height > 0 && layoutMeasurement?.height > 0) {
              // Fresher than the last onLayout / onContentSizeChange (read from the live view).
              metrics.current.content = contentSize.height;
              metrics.current.viewport = layoutMeasurement.height;
              maxY = contentSize.height - layoutMeasurement.height;
            }
            scroller.current?.onScroll(contentOffset.y, maxY);
          }}
          onScrollBeginDrag={() => scroller.current?.stop()}
          onTouchStart={() => scroller.current?.stop()}>
          <View
            ref={contentRef}
            collapsable={false}
            testID="source-content"
            style={[styles.panes, wide ? { flexDirection: dir.row } : null]}>
            {imagePane}
            {listPane}
          </View>
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
