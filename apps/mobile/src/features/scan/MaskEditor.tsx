// "Hide parts" mask editor (D-19, PRODUCT_SPEC S5). Drag on the page to draw a black box, or tap
// to place a box (the non-drag alternative). A placed box can be selected (tap it or its row):
// drag its body to move it, drag the corner handle to resize it, or use the row's buttons (move
// up / down / left / right, bigger, smaller — the non-drag alternative); every box keeps Remove.
// Uses React Native's core responder props so it works on web and native without a
// gesture-handler root view (none is mounted by the app shell). Coordinates are normalised to the
// upright page image.

import { Image } from 'expo-image';
import { useRef, useState } from 'react';
import { AccessibilityInfo, type GestureResponderEvent, type LayoutChangeEvent, Modal, Pressable, ScrollView, StyleSheet, View } from 'react-native';

import type { MaskRect } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { keyExists, t as tr } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { PAGE_IMAGE_KEY } from './choices';
import { hitTestMask, MASK_STEP, maskAround, maskFromDrag, moveMask, replaceMask, resizeFromCorner, resizeMask } from './masks';
import { ltrBox } from '@/design/ltr';

export interface MaskEditorProps {
  page: CapturedPage;
  pageNumber: number;
  /** Pages in this scan (for the "Page {n} of {count}" label). */
  pageCount?: number;
  visible: boolean;
  onChange(masks: MaskRect[]): void;
  onClose(): void;
}

type Point = { x: number; y: number };
type Gesture = { local: Point; page: Point; mode: 'draw' | 'move' | 'resize'; index: number | null; orig: MaskRect | null };

/** "Box {i} added, covering part of page {n}" (PRODUCT_SPEC S5). */
export const MASK_ADDED_KEY = 'a11y.mask_added';

/** Row / handle copy (keys-2c-mobilescan.json); up/down reuse the page-reorder words. */
export const MASK_KEYS = {
  box: 'review.mask_box',
  up: 'review.move_up',
  down: 'review.move_down',
  left: 'review.mask_move_left',
  right: 'review.mask_move_right',
  bigger: 'review.mask_bigger',
  smaller: 'review.mask_smaller',
  handle: 'review.mask_resize_handle',
} as const;

function announceMask(i: number, n: number) {
  if (!keyExists(MASK_ADDED_KEY)) return;
  try {
    AccessibilityInfo.announceForAccessibility(tr(MASK_ADDED_KEY, { i, n }));
  } catch {
    // best-effort
  }
}

export function MaskEditor({ page, pageNumber, pageCount, visible, onChange, onClose }: MaskEditorProps) {
  const t = useT();
  const { colors } = useTheme();
  const dir = useDirection();
  const [box, setBox] = useState({ width: 0, height: 0 });
  // The box being drawn / moved / resized (`index` null while drawing a new one).
  const [draft, setDraft] = useState<{ rect: MaskRect; index: number | null } | null>(null);
  const [selected, setSelected] = useState<number | null>(page.masks.length ? page.masks.length - 1 : null);
  const gesture = useRef<Gesture | null>(null);
  const aspect = page.width && page.height ? page.height / page.width : 1.294;
  const masks = page.masks;

  const add = (m: MaskRect) => {
    onChange([...masks, m]);
    setSelected(masks.length);
    announceMask(masks.length + 1, pageNumber);
  };
  const update = (i: number, m: MaskRect) => onChange(replaceMask(masks, i, m));
  const remove = (i: number) => {
    onChange(masks.filter((_, j) => j !== i));
    setSelected(null);
  };

  const delta = (e: GestureResponderEvent, g: Gesture) => ({
    dx: (e.nativeEvent.pageX - g.page.x) / (box.width || 1),
    dy: (e.nativeEvent.pageY - g.page.y) / (box.height || 1),
  });

  const shaped = (e: GestureResponderEvent, g: Gesture): MaskRect | null => {
    if (g.mode === 'draw') {
      const end = { x: g.local.x + (e.nativeEvent.pageX - g.page.x), y: g.local.y + (e.nativeEvent.pageY - g.page.y) };
      return maskFromDrag(g.local, end, box);
    }
    if (!g.orig) return null;
    const { dx, dy } = delta(e, g);
    return g.mode === 'move' ? moveMask(g.orig, dx, dy) : resizeFromCorner(g.orig, dx, dy);
  };

  // Plain responder props (no PanResponder object): handlers run only in events.
  const responder = {
    onStartShouldSetResponder: () => true,
    onMoveShouldSetResponder: () => true,
    onResponderGrant: (e: GestureResponderEvent) => {
      const local = { x: e.nativeEvent.locationX, y: e.nativeEvent.locationY };
      const hit = hitTestMask(masks, local, box, selected);
      if (hit) setSelected(hit.index);
      gesture.current = {
        local,
        page: { x: e.nativeEvent.pageX, y: e.nativeEvent.pageY },
        mode: hit ? (hit.kind === 'handle' ? 'resize' : 'move') : 'draw',
        index: hit ? hit.index : null,
        orig: hit ? masks[hit.index] : null,
      };
    },
    // Keep the drag when the surrounding ScrollView would like to scroll instead.
    onResponderTerminationRequest: () => false,
    onResponderMove: (e: GestureResponderEvent) => {
      const g = gesture.current;
      const rect = g ? shaped(e, g) : null;
      setDraft(g && rect ? { rect, index: g.mode === 'draw' ? null : g.index } : null);
    },
    onResponderRelease: (e: GestureResponderEvent) => {
      const g = gesture.current;
      gesture.current = null;
      setDraft(null);
      if (!g) return;
      const moved = Math.abs(e.nativeEvent.pageX - g.page.x) > 8 || Math.abs(e.nativeEvent.pageY - g.page.y) > 8;
      if (g.mode !== 'draw') {
        // A tap on a box only selects it; a drag moves or resizes it.
        const next = moved ? shaped(e, g) : null;
        if (next && g.index !== null) update(g.index, next);
        return;
      }
      const dragged = moved ? maskFromDrag(g.local, { x: g.local.x + (e.nativeEvent.pageX - g.page.x), y: g.local.y + (e.nativeEvent.pageY - g.page.y) }, box) : null;
      const next = dragged ?? (box.width > 0 && box.height > 0 ? maskAround({ x: g.local.x / box.width, y: g.local.y / box.height }) : null);
      if (next) add(next);
    },
    onResponderTerminate: () => {
      gesture.current = null;
      setDraft(null);
    },
  };

  const onLayout = (e: LayoutChangeEvent) => {
    const w = e.nativeEvent.layout.width;
    setBox({ width: w, height: w * aspect });
  };

  const rectStyle = (m: MaskRect) => ({
    left: m.x0 * box.width,
    top: m.y0 * box.height,
    width: (m.x1 - m.x0) * box.width,
    height: (m.y1 - m.y0) * box.height,
  });

  const editing = draft?.index ?? null;
  const sel = selected !== null && selected < masks.length ? selected : null;

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} transparent={false}>
      <ScrollView style={{ backgroundColor: colors.background }} contentContainerStyle={styles.body} scrollEnabled={!draft}>
        <Heading level={1}>{t('review.hide_parts')}</Heading>
        <AppText>{t('review.hide_tip')}</AppText>
        <AppText color="textMuted">{t('review.hide_note_receipt')}</AppText>
        <View
          testID="mask-canvas"
          onLayout={onLayout}
          style={[styles.canvas, { height: box.height || 320, borderColor: colors.border }]}
          accessibilityLabel={`${t(PAGE_IMAGE_KEY, { n: pageNumber, count: pageCount ?? pageNumber })}. ${t('review.hide_tip')}`}
          {...responder}>
          <View pointerEvents="none" style={StyleSheet.absoluteFill}>
            <Image source={{ uri: page.uri }} cachePolicy="memory" contentFit="fill" style={StyleSheet.absoluteFill} />
          </View>
          {masks.map((m, i) =>
            draft && editing === i ? null : (
              <View
                key={`m-${i}`}
                testID={`mask-box-${i + 1}`}
                pointerEvents="none"
                style={[styles.mask, rectStyle(m), i === sel ? { borderColor: colors.focus, borderWidth: 3 } : null]}
              />
            ),
          )}
          {sel !== null && !draft ? (
            <View
              testID={`mask-handle-${sel + 1}`}
              pointerEvents="none"
              accessibilityLabel={t(MASK_KEYS.handle, { i: sel + 1 })}
              style={[styles.handle, { left: masks[sel].x1 * box.width - 12, top: masks[sel].y1 * box.height - 12, borderColor: colors.focus, backgroundColor: colors.surfaceRaised }]}
            />
          ) : null}
          {draft ? <View pointerEvents="none" style={[styles.draft, { borderColor: colors.focus }, rectStyle(draft.rect)]} /> : null}
        </View>
        {masks.map((m, i) => (
          <View key={`row-${i}`} testID={`mask-row-${i + 1}`} style={[styles.row, { borderColor: colors.divider }]}>
            <View style={[styles.rowHead, { flexDirection: dir.row }]}>
              <Pressable
                role="button"
                accessibilityState={{ selected: i === sel }}
                accessibilityLabel={t(MASK_KEYS.box, { i: i + 1 })}
                hitSlop={size.hitSlop}
                onPress={() => setSelected(i)}
                style={[styles.flex, styles.rowName, { flexDirection: dir.row }]}>
                <View style={[styles.swatch, i === sel ? { borderColor: colors.focus, borderWidth: 2 } : null]} />
                <AppText weight={i === sel ? 'bold' : 'regular'}>{t(MASK_KEYS.box, { i: i + 1 })}</AppText>
              </Pressable>
              <RowButton label={t('review.remove')} danger onPress={() => remove(i)} a11y={`${t('review.remove')} ${i + 1}`} />
            </View>
            {i === sel ? (
              <View style={[styles.tools, { flexDirection: dir.row }]}>
                <RowButton label={t(MASK_KEYS.up)} onPress={() => update(i, moveMask(m, 0, -MASK_STEP.move))} />
                <RowButton label={t(MASK_KEYS.down)} onPress={() => update(i, moveMask(m, 0, MASK_STEP.move))} />
                {/* The page is never mirrored, so left / right are the page's own directions. */}
                <RowButton label={t(MASK_KEYS.left)} onPress={() => update(i, moveMask(m, -MASK_STEP.move, 0))} />
                <RowButton label={t(MASK_KEYS.right)} onPress={() => update(i, moveMask(m, MASK_STEP.move, 0))} />
                <RowButton label={t(MASK_KEYS.bigger)} onPress={() => update(i, resizeMask(m, MASK_STEP.grow.w, MASK_STEP.grow.h))} />
                <RowButton label={t(MASK_KEYS.smaller)} onPress={() => update(i, resizeMask(m, -MASK_STEP.grow.w, -MASK_STEP.grow.h))} />
              </View>
            ) : null}
          </View>
        ))}
        <BigButton label={t('review.hide_parts')} icon="lock" variant="secondary" size={56} onPress={() => add(maskAround({ x: 0.5, y: 0.5 }))} />
        <BigButton label={t('capture.done')} icon="check" variant="primary" size={72} onPress={onClose} />
      </ScrollView>
    </Modal>
  );
}

function RowButton({ label, onPress, danger, a11y }: { label: string; onPress(): void; danger?: boolean; a11y?: string }) {
  const { colors } = useTheme();
  const color = danger ? colors.danger : colors.primary;
  return (
    <Pressable role="button" accessibilityLabel={a11y ?? label} hitSlop={size.hitSlop} onPress={onPress} style={[styles.small, { borderColor: color }]}>
      <AppText variant="caption" weight="bold" colorValue={color}>
        {label}
      </AppText>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  body: { padding: space.screenGutter, gap: space.lg, maxWidth: 720, width: '100%', alignSelf: 'center' },
  // The page is never mirrored in RTL.
  canvas: { width: '100%', borderWidth: 1, overflow: 'hidden', ...ltrBox },
  mask: { position: 'absolute', backgroundColor: '#000000' },
  draft: { position: 'absolute', backgroundColor: 'rgba(0,0,0,0.6)', borderWidth: 2 },
  handle: { position: 'absolute', width: 24, height: 24, borderRadius: 12, borderWidth: 3 },
  row: { gap: space.sm, borderTopWidth: StyleSheet.hairlineWidth, paddingTop: space.sm },
  rowHead: { alignItems: 'center', gap: space.sm },
  rowName: { minHeight: size.minTouch, alignItems: 'center', gap: space.sm },
  tools: { flexWrap: 'wrap', gap: space.xs },
  swatch: { width: 24, height: 12, backgroundColor: '#000000' },
  flex: { flex: 1 },
  small: { minHeight: size.minTouch, justifyContent: 'center', borderWidth: 2, borderRadius: radius.pill, paddingHorizontal: space.md },
});
