// "Hide parts" move / resize (D-19, PRODUCT_SPEC S5): the pure geometry (`hitTestMask`,
// `resizeFromCorner`, `replaceMask`) and the MaskEditor gestures — drag a box's body to move it,
// drag the selected box's corner handle to resize it, a tap on a box only selects it, a drag on
// the empty page draws a new box, a tap there places one — plus the row buttons (the non-drag
// alternative: up / down / left / right, bigger, smaller, remove). New copy keys come from
// keys-2c-mobilescan.json, so the test pack carries English for them until the COPY merge.

import { fireEvent, render } from '@testing-library/react-native';
import { useState } from 'react';

import type { MaskRect } from '@/api/types';
import { AppProviders } from '@/design/components/Providers';
import { EN_PACK, t, useI18n } from '@/i18n/store';
import type { CapturedPage } from '@/store/session';

import { PAGE_IMAGE_KEY } from './choices';
import { MASK_KEYS, MaskEditor } from './MaskEditor';
import { hitTestMask, MASK_STEP, maskAround, replaceMask, resizeFromCorner } from './masks';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const STRINGS: Record<string, string> = {
  [PAGE_IMAGE_KEY]: 'Page {n} of {count}',
  [MASK_KEYS.box]: 'Box {i}',
  [MASK_KEYS.left]: 'Move left',
  [MASK_KEYS.right]: 'Move right',
  [MASK_KEYS.bigger]: 'Bigger',
  [MASK_KEYS.smaller]: 'Smaller',
  [MASK_KEYS.handle]: 'Drag to change the size of box {i}',
};

const VIEW = { width: 1000, height: 1000 };
const BOX: MaskRect = { x0: 0.2, y0: 0.2, x1: 0.4, y1: 0.3 };

function testPack() {
  useI18n.getState().setPack({ ...EN_PACK, strings: { ...EN_PACK.strings, ...STRINGS } });
}

function pg(masks: MaskRect[]): CapturedPage {
  // Square page, so a 1000-px-wide canvas is 1000 × 1000 and pixels map to page units / 1000.
  return { id: 'p', uri: 'data:image/jpeg;base64,AA', mimeType: 'image/jpeg', width: 1000, height: 1000, rotation: 0, masks, source: 'camera' };
}

/** Holds the masks like ReviewScreen does; `changes` records every onChange. */
function Harness({ initial, changes }: { initial: MaskRect[]; changes: MaskRect[][] }) {
  const [masks, setMasks] = useState(initial);
  return (
    <AppProviders staticMetrics>
      <MaskEditor
        page={pg(masks)}
        pageNumber={1}
        pageCount={2}
        visible
        onChange={(m) => {
          changes.push(m);
          setMasks(m);
        }}
        onClose={() => undefined}
      />
    </AppProviders>
  );
}

async function renderEditor(initial: MaskRect[]) {
  testPack();
  const changes: MaskRect[][] = [];
  const view = await render(<Harness initial={initial} changes={changes} />);
  const canvas = view.getByTestId('mask-canvas');
  await fireEvent(canvas, 'layout', { nativeEvent: { layout: { width: 1000, height: 1000, x: 0, y: 0 } } });
  const ev = (x: number, y: number) => ({ nativeEvent: { locationX: x, locationY: y, pageX: x, pageY: y } });
  const drag = async (from: [number, number], to: [number, number]) => {
    await fireEvent(view.getByTestId('mask-canvas'), 'responderGrant', ev(...from));
    await fireEvent(view.getByTestId('mask-canvas'), 'responderMove', ev(...to));
    await fireEvent(view.getByTestId('mask-canvas'), 'responderRelease', ev(...to));
  };
  const last = () => changes[changes.length - 1];
  return { ...view, changes, drag, last };
}

afterEach(() => {
  useI18n.getState().setPack(EN_PACK);
});

describe('mask geometry', () => {
  it('hitTestMask: the selected corner handle, else the top-most box, else nothing', () => {
    expect(hitTestMask([BOX], { x: 400, y: 300 }, VIEW, 0)).toEqual({ kind: 'handle', index: 0 });
    // Within the 22-px handle radius, even just outside the box.
    expect(hitTestMask([BOX], { x: 415, y: 315 }, VIEW, 0)).toEqual({ kind: 'handle', index: 0 });
    expect(hitTestMask([BOX], { x: 300, y: 250 }, VIEW, 0)).toEqual({ kind: 'body', index: 0 });
    // An unselected box has no handle: its corner is just its body.
    expect(hitTestMask([BOX], { x: 400, y: 300 }, VIEW, null)).toEqual({ kind: 'body', index: 0 });
    expect(hitTestMask([BOX], { x: 900, y: 900 }, VIEW, 0)).toBeNull();
    const over: MaskRect = { x0: 0.3, y0: 0.25, x1: 0.6, y1: 0.5 };
    expect(hitTestMask([BOX, over], { x: 350, y: 280 }, VIEW, null)).toEqual({ kind: 'body', index: 1 });
    expect(hitTestMask([BOX], { x: 300, y: 250 }, { width: 0, height: 0 }, 0)).toBeNull();
  });

  it('resizeFromCorner keeps the top-left corner, a minimum size and the page edge', () => {
    expect(resizeFromCorner(BOX, 0.1, 0.1)).toEqual({ x0: 0.2, y0: 0.2, x1: 0.5, y1: expect.closeTo(0.4, 5) });
    expect(resizeFromCorner(BOX, -1, -1)).toEqual({ x0: 0.2, y0: 0.2, x1: expect.closeTo(0.22, 5), y1: expect.closeTo(0.21, 5) });
    expect(resizeFromCorner(BOX, 5, 5)).toEqual({ x0: 0.2, y0: 0.2, x1: 1, y1: 1 });
  });

  it('replaceMask swaps one box without mutating; a bad index changes nothing', () => {
    const masks = [BOX, maskAround({ x: 0.5, y: 0.8 })];
    const next: MaskRect = { x0: 0.1, y0: 0.1, x1: 0.2, y1: 0.2 };
    const out = replaceMask(masks, 1, next);
    expect(out).toEqual([BOX, next]);
    expect(masks[1]).not.toEqual(next);
    expect(replaceMask(masks, 5, next)).toEqual(masks);
    expect(replaceMask(masks, -1, next)).not.toBe(masks);
  });
});

describe('MaskEditor move / resize', () => {
  it('labels the canvas and shows the selected box with its corner handle', async () => {
    const s = await renderEditor([BOX]);
    expect(s.getByLabelText(new RegExp(t(PAGE_IMAGE_KEY, { n: 1, count: 2 })))).toBeTruthy();
    expect(s.getByTestId('mask-handle-1').props.accessibilityLabel).toBe(t(MASK_KEYS.handle, { i: 1 }));
  });

  it('row buttons move and resize the selected box (the non-drag alternative)', async () => {
    const s = await renderEditor([BOX]);
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.left)));
    expect(s.last()[0].x0).toBeCloseTo(0.2 - MASK_STEP.move, 5);
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.right)));
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.right)));
    expect(s.last()[0].x0).toBeCloseTo(0.2 + MASK_STEP.move, 5);
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.up)));
    expect(s.last()[0].y0).toBeCloseTo(0.2 - MASK_STEP.move, 5);
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.down)));
    expect(s.last()[0].y0).toBeCloseTo(0.2, 5);
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.bigger)));
    expect(s.last()[0].x1 - s.last()[0].x0).toBeCloseTo(0.2 + MASK_STEP.grow.w, 5);
    expect(s.last()[0].y1 - s.last()[0].y0).toBeCloseTo(0.1 + MASK_STEP.grow.h, 5);
    await fireEvent.press(s.getByLabelText(t(MASK_KEYS.smaller)));
    expect(s.last()[0].x1 - s.last()[0].x0).toBeCloseTo(0.2, 5);
    expect(s.last()).toHaveLength(1);
  });

  it('dragging a box body moves it; dragging the corner handle resizes it', async () => {
    const s = await renderEditor([BOX]);
    await s.drag([250, 250], [350, 350]);
    expect(s.last()).toHaveLength(1);
    expect(s.last()[0]).toEqual({ x0: expect.closeTo(0.3, 5), y0: expect.closeTo(0.3, 5), x1: expect.closeTo(0.5, 5), y1: expect.closeTo(0.4, 5) });
    // The handle sits on the moved box's bottom-right corner (500, 400).
    await s.drag([500, 400], [600, 500]);
    expect(s.last()).toHaveLength(1);
    expect(s.last()[0]).toEqual({ x0: expect.closeTo(0.3, 5), y0: expect.closeTo(0.3, 5), x1: expect.closeTo(0.6, 5), y1: expect.closeTo(0.5, 5) });
  });

  it('a tap on a box only selects it (no change)', async () => {
    const other: MaskRect = { x0: 0.6, y0: 0.6, x1: 0.8, y1: 0.7 };
    const s = await renderEditor([BOX, other]);
    expect(s.getByTestId('mask-handle-2')).toBeTruthy();
    await s.drag([300, 250], [303, 252]);
    expect(s.changes).toHaveLength(0);
    expect(s.getByTestId('mask-handle-1')).toBeTruthy();
    expect(s.queryByTestId('mask-handle-2')).toBeNull();
  });

  it('a drag on the empty page draws a new box; a tap there places one', async () => {
    const s = await renderEditor([BOX]);
    await s.drag([600, 600], [800, 700]);
    expect(s.last()).toHaveLength(2);
    expect(s.last()[1]).toEqual({ x0: expect.closeTo(0.6, 5), y0: expect.closeTo(0.6, 5), x1: expect.closeTo(0.8, 5), y1: expect.closeTo(0.7, 5) });
    expect(s.getByTestId('mask-handle-2')).toBeTruthy();
    await s.drag([100, 900], [100, 900]);
    expect(s.last()).toHaveLength(3);
    expect(s.last()[2]).toEqual(maskAround({ x: 0.1, y: 0.9 }));
  });

  it('Remove deletes the box', async () => {
    const s = await renderEditor([BOX]);
    await fireEvent.press(s.getByLabelText(`${t('review.remove')} 1`));
    expect(s.last()).toEqual([]);
    expect(s.queryByTestId('mask-box-1')).toBeNull();
  });
});
