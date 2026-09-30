// S8 `?block=` initial scroll (PRODUCT_SPEC S7 item 8 "tap → S8 scrolled to the block", S8 route).
// WP5 verifier failure: on web the first scroll ran while the pane was still unbounded (a no-op)
// and was never retried. These tests pin the fix: nothing scrolls until the pane is bounded and the
// ScrollView reports that height; the scroll is re-issued until the offset confirms; late layout
// changes keep the block in place for a short settle window; any user movement ends it for good.

import { act, fireEvent, render } from '@testing-library/react-native';
import { Dimensions, ScrollView, View } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import type { AnalysisResult } from '@/api/types';
import { EN_PACK, useI18n } from '@/i18n/store';
import { resetVoicesForTests } from '@/lib/tts';

import medicaidEn from '../../../assets/fixtures/medicaid_address_confirmation.result.en.json';
import {
  blockScrollTarget,
  INITIAL_SCROLL_MAX_MS,
  INITIAL_SCROLL_MAX_TRIES,
  InitialBlockScroll,
  type InitialScrollDeps,
  type ScrollMetrics,
  scrollMetricsReady,
  SETTLE_MS,
  SourceScreen,
} from './SourceScreen';
import { blockLabel, sourcePageModel } from './sourceModel';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

jest.mock('expo-router', () => ({
  router: { back: jest.fn(), replace: jest.fn(), push: jest.fn(), canGoBack: () => true },
  useLocalSearchParams: () => ({}),
  Stack: { Screen: () => null },
}));

jest.mock('expo-speech', () => ({
  getAvailableVoicesAsync: () => Promise.resolve([]),
  speak: jest.fn(),
  stop: () => Promise.resolve(),
  isSpeakingAsync: () => Promise.resolve(false),
  maxSpeechInputLength: 4000,
  VoiceQuality: { Default: 'Default', Enhanced: 'Enhanced' },
}));

const GAP = 12; // space.md

// ---------------------------------------------------------------------------------------------
// Pure target math

describe('blockScrollTarget', () => {
  const bounded: ScrollMetrics = { paneHeight: 600, viewport: 600, content: 2000 };

  it('waits while the pane is unbounded or its viewport still shows the pre-bound height', () => {
    expect(blockScrollTarget(900, { paneHeight: null, viewport: 2000, content: 2000 })).toBeNull();
    // paneHeight is known, but the ScrollView has not re-laid out yet (viewport = content height).
    expect(blockScrollTarget(900, { paneHeight: 600, viewport: 2000, content: 2000 })).toBeNull();
    expect(blockScrollTarget(900, { paneHeight: 600, viewport: null, content: 2000 })).toBeNull();
    expect(blockScrollTarget(900, { paneHeight: 600, viewport: 600, content: null })).toBeNull();
    expect(blockScrollTarget(null, bounded)).toBeNull();
    expect(scrollMetricsReady(bounded)).toBe(true);
  });

  it('puts the block a small gap below the top, clamped to what can scroll', () => {
    expect(blockScrollTarget(900, bounded)).toBe(900 - GAP);
    expect(blockScrollTarget(5, bounded)).toBe(0);
    expect(blockScrollTarget(1900, bounded)).toBe(1400); // content − viewport
    expect(blockScrollTarget(300, { paneHeight: 600, viewport: 600, content: 500 })).toBe(0); // all fits
  });
});

// ---------------------------------------------------------------------------------------------
// Controller with fake frames / timers / clock

function harness(initial: Partial<ScrollMetrics> = {}) {
  const m: ScrollMetrics = { paneHeight: null, viewport: 2400, content: 2400, ...initial };
  const env = {
    metrics: m,
    blockY: 1400 as number | null,
    now: 0,
    frames: [] as (() => void)[],
    timers: [] as { at: number; cb: () => void }[],
    scrolls: [] as number[],
  };
  const deps: InitialScrollDeps = {
    measure: (done) => done(env.blockY),
    metrics: () => env.metrics,
    scrollTo: (y) => env.scrolls.push(y),
    frame: (cb) => {
      env.frames.push(cb);
      return () => {
        env.frames = env.frames.filter((f) => f !== cb);
      };
    },
    timer: (cb, ms) => {
      const t = { at: env.now + ms, cb };
      env.timers.push(t);
      return () => {
        env.timers = env.timers.filter((x) => x !== t);
      };
    },
    now: () => env.now,
  };
  const s = new InitialBlockScroll(deps);
  /** Run queued frames (and frames they queue) up to `n` rounds. */
  const flush = (n = 5) => {
    for (let i = 0; i < n && env.frames.length; i++) {
      const due = env.frames;
      env.frames = [];
      due.forEach((f) => f());
    }
  };
  const advance = (ms: number) => {
    env.now += ms;
    const due = env.timers.filter((t) => t.at <= env.now);
    env.timers = env.timers.filter((t) => t.at > env.now);
    due.forEach((t) => t.cb());
  };
  return { s, env, flush, advance };
}

describe('InitialBlockScroll', () => {
  it('does not scroll while the pane is unbounded, then scrolls once it is (the WP5 web bug)', () => {
    const { s, env, flush } = harness();
    s.start();
    flush();
    expect(env.scrolls).toEqual([]); // before the fix this "scrolled" into the void and gave up
    expect(s.state).toBe('pending');

    env.metrics.paneHeight = 636; // pane bounded, ScrollView not re-measured yet
    s.kick();
    flush();
    expect(env.scrolls).toEqual([]);

    env.metrics.viewport = 636; // ScrollView onLayout with the bounded height
    s.kick();
    flush(1);
    expect(env.scrolls).toEqual([1400 - GAP]);
  });

  it('re-issues the scroll on the next frames until the offset confirms, then settles and lets go', () => {
    const { s, env, flush, advance } = harness({ paneHeight: 636, viewport: 636 });
    s.start();
    flush(3); // the web ScrollView ignored the first commands (offset still 0)
    expect(env.scrolls).toEqual([1388, 1388, 1388]);

    s.onScroll(1388, 2400 - 636); // the scroll landed
    flush();
    expect(env.scrolls).toHaveLength(3); // confirmed: nothing more issued
    expect(s.state).toBe('settling');

    advance(SETTLE_MS);
    expect(s.state).toBe('done');
    env.blockY = 200;
    s.kick();
    flush();
    expect(env.scrolls).toHaveLength(3);
  });

  it('keeps the block in place when the layout moves it during the settle window', () => {
    const { s, env, flush } = harness({ paneHeight: 636, viewport: 636 });
    s.start();
    flush(1);
    s.onScroll(1388);
    flush();
    expect(s.state).toBe('settling');

    env.blockY = 1800; // e.g. the page image above the list got its real height
    env.metrics.content = 3000;
    s.kick();
    flush(1);
    expect(env.scrolls).toEqual([1388, 1788]);
    s.onScroll(1788);
    flush();
    expect(s.state).toBe('settling');
  });

  it('never fights the user: their scroll or touch ends it for good', () => {
    const scrolled = harness({ paneHeight: 636, viewport: 636 });
    scrolled.s.start();
    scrolled.flush(1);
    scrolled.s.onScroll(1388);
    scrolled.s.onScroll(900); // user wheel / keyboard / scrollbar
    expect(scrolled.s.state).toBe('done');
    scrolled.env.blockY = 1800;
    scrolled.s.kick();
    scrolled.flush();
    expect(scrolled.env.scrolls).toEqual([1388]);

    const early = harness(); // user scrolls before the pane was even bounded
    early.s.start();
    early.s.onScroll(120);
    early.env.metrics.paneHeight = 636;
    early.env.metrics.viewport = 636;
    early.s.kick();
    early.flush();
    expect(early.env.scrolls).toEqual([]);

    const touched = harness({ paneHeight: 636, viewport: 636 });
    touched.s.start();
    touched.s.stop(); // onTouchStart / onScrollBeginDrag / a tap on a block / page change
    touched.flush();
    expect(touched.env.scrolls).toEqual([]);
  });

  it('treats a scroll clamped at the end of the content as its own', () => {
    const { s, env, flush } = harness({ paneHeight: 636, viewport: 636 });
    s.start();
    flush(1);
    expect(env.scrolls).toEqual([1388]);
    s.onScroll(1300, 1300); // content shrank a little: the browser clamped to its max
    expect(s.state).toBe('pending');
  });

  it('settles at once when the block is already in view, and gives up after its budgets', () => {
    const fits = harness({ paneHeight: 636, viewport: 636, content: 500 });
    fits.s.start();
    fits.flush();
    expect(fits.env.scrolls).toEqual([]);
    expect(fits.s.state).toBe('settling');

    const stuck = harness({ paneHeight: 636, viewport: 636 });
    stuck.s.start();
    stuck.flush(INITIAL_SCROLL_MAX_TRIES + 5);
    expect(stuck.env.scrolls).toHaveLength(INITIAL_SCROLL_MAX_TRIES);
    expect(stuck.s.state).toBe('done');

    const late = harness();
    late.s.start();
    late.flush();
    late.env.now = INITIAL_SCROLL_MAX_MS + 1; // pane only bounded long after opening
    late.env.metrics.paneHeight = 636;
    late.env.metrics.viewport = 636;
    late.s.kick();
    late.flush();
    expect(late.env.scrolls).toEqual([]);
    expect(late.s.state).toBe('done');
  });
});

// ---------------------------------------------------------------------------------------------
// SourceScreen wiring: live block measurement, bounded pane, user takeover, tap to scroll

type Proto = Record<string, (...args: never[]) => unknown>;
const viewProto = (View as unknown as { prototype: Proto }).prototype;
const scrollProto = (ScrollView as unknown as { prototype: Proto }).prototype;
const METRICS = { frame: { x: 0, y: 0, width: 390, height: 844 }, insets: { top: 0, left: 0, right: 0, bottom: 0 } };
const PANE_TOP = 100;
const CONTENT = 4000;
/** Live block tops relative to the scroll content (what measureLayout reports). */
const BLOCK_Y: Record<string, number> = { 'source-block-p1b9': 1500, 'source-block-p1b2': 400 };

describe('SourceScreen ?block= initial scroll', () => {
  let paneMeasured = false;
  let scrollTo: jest.SpyInstance;
  // The preset's native methods are already shared jest.fn()s, so spyOn hands those back: reset
  // them after each test instead of relying on restoreAllMocks.
  let spies: jest.SpyInstance[] = [];

  beforeEach(() => {
    jest.useFakeTimers();
    resetVoicesForTests();
    paneMeasured = false;
    const inWindow = jest.spyOn(viewProto, 'measureInWindow').mockImplementation(function (cb: (x: number, y: number, w: number, h: number) => void) {
      if (paneMeasured) cb(0, PANE_TOP, 390, 0);
    } as never);
    const measureLayout = jest.spyOn(viewProto, 'measureLayout').mockImplementation(function (
      this: { props: { testID?: string } },
      _relativeTo: unknown,
      ok: (x: number, y: number, w: number, h: number) => void,
    ) {
      const y = BLOCK_Y[this.props.testID ?? ''];
      if (y !== undefined) ok(0, y, 360, 60);
    } as never);
    // Like the platforms: a scroll command emits one onScroll at the new offset.
    scrollTo = jest.spyOn(scrollProto, 'scrollTo').mockImplementation(function (
      this: { props: { onScroll?: (e: unknown) => void } },
      opts: { y: number },
    ) {
      this.props.onScroll?.(scrollEvent(opts.y, paneHeight()));
    } as never);
    spies = [inWindow, measureLayout, scrollTo];
  });

  afterEach(() => {
    spies.forEach((spy) => spy.mockReset());
    jest.restoreAllMocks();
    jest.useRealTimers();
    useI18n.getState().setPack(EN_PACK);
  });

  const paneHeight = () => Math.max(280, Dimensions.get('window').height - PANE_TOP);
  const layout = (height: number) => ({ nativeEvent: { layout: { x: 0, y: 0, width: 360, height } } });
  function scrollEvent(y: number, viewport: number) {
    return {
      nativeEvent: {
        contentOffset: { x: 0, y },
        contentSize: { width: 360, height: CONTENT },
        layoutMeasurement: { width: 360, height: viewport },
      },
    };
  }
  const frames = async (ms = 100) => {
    await act(async () => {
      jest.advanceTimersByTime(ms);
    });
  };

  async function open(block: string | null) {
    const a = JSON.parse(JSON.stringify(medicaidEn)) as AnalysisResult;
    const utils = await render(
      <SafeAreaProvider initialMetrics={METRICS}>
        <SourceScreen analysis={a} pages={[]} block={block} page="1" />
      </SafeAreaProvider>,
    );
    return { ...utils, a };
  }

  /** The web order of events: unbounded layout first, then the measured pane top, then the
   *  ScrollView re-laid out at the bounded height. */
  async function layOut(utils: Awaited<ReturnType<typeof open>>) {
    const sv = utils.getByTestId('source-scroll');
    await fireEvent(sv, 'layout', layout(CONTENT));
    await fireEvent(sv, 'contentSizeChange', 360, CONTENT);
    await frames();
    expect(scrollTo).not.toHaveBeenCalled(); // unbounded: scrolling now would be a silent no-op

    paneMeasured = true;
    await fireEvent(utils.getByTestId('source-panes'), 'layout', layout(CONTENT));
    await frames();
    expect(utils.getByTestId('source-panes')).toHaveStyle({ height: paneHeight() });
    expect(scrollTo).not.toHaveBeenCalled(); // bounded, but the viewport still reads the old height

    await fireEvent(sv, 'layout', layout(paneHeight()));
    await frames();
    return sv;
  }

  it('scrolls to the live-measured block once the pane is bounded, exactly once', async () => {
    const utils = await open('p1b9');
    const sv = await layOut(utils);
    expect(scrollTo).toHaveBeenCalledTimes(1);
    expect(scrollTo).toHaveBeenCalledWith({ y: 1500 - GAP, animated: false });

    // A late layout change within the settle window keeps the block in place…
    BLOCK_Y['source-block-p1b9'] = 1700;
    await fireEvent(sv, 'contentSizeChange', 360, CONTENT);
    await frames();
    expect(scrollTo).toHaveBeenLastCalledWith({ y: 1700 - GAP, animated: false });
    BLOCK_Y['source-block-p1b9'] = 1500;

    // …and after it, nothing moves on its own again.
    await frames(SETTLE_MS + 100);
    const calls = scrollTo.mock.calls.length;
    await fireEvent(sv, 'contentSizeChange', 360, CONTENT);
    await frames();
    expect(scrollTo).toHaveBeenCalledTimes(calls);
  });

  it('stops for good when the user scrolls, and a tap scrolls (animated) to the live position', async () => {
    const utils = await open('p1b9');
    const sv = await layOut(utils);
    expect(scrollTo).toHaveBeenCalledTimes(1);

    await fireEvent(sv, 'scroll', scrollEvent(600, paneHeight())); // the user's own scroll
    BLOCK_Y['source-block-p1b9'] = 1800;
    await fireEvent(sv, 'contentSizeChange', 360, CONTENT);
    await frames();
    BLOCK_Y['source-block-p1b9'] = 1500;
    expect(scrollTo).toHaveBeenCalledTimes(1);

    const row = sourcePageModel(utils.a, 1).blocks.find((r) => r.block.id === 'p1b2');
    if (!row) throw new Error('fixture block p1b2 missing');
    await fireEvent.press(utils.getByLabelText(blockLabel(row, 1)));
    expect(scrollTo).toHaveBeenLastCalledWith({ y: 400 - GAP, animated: true });
  });

  it('a touch before the layout settles cancels the initial scroll', async () => {
    const touched = await open('p1b9');
    await fireEvent(touched.getByTestId('source-scroll'), 'touchStart');
    await layOut(touched);
    expect(scrollTo).not.toHaveBeenCalled();
  });

  it('without ?block= it never scrolls on its own', async () => {
    const plain = await open(null);
    await layOut(plain);
    expect(scrollTo).not.toHaveBeenCalled();
  });
});
