// "Hide parts" mask editor (D-19, PRODUCT_SPEC S5). Drag on the page to draw a black box, or tap
// to place a box (the non-drag alternative); every box has a Remove button. Uses React Native's
// core responder props so it works on web and native without a gesture-handler root view (none
// is mounted by the app shell). Coordinates are normalised to the upright page image.

import { Image } from 'expo-image';
import { useRef, useState } from 'react';
import {
  AccessibilityInfo,
  type GestureResponderEvent,
  type LayoutChangeEvent,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from 'react-native';

import type { MaskRect } from '@/api/types';
import { BigButton } from '@/design/components/BigButton';
import { AppText, Heading } from '@/design/components/Text';
import { useTheme } from '@/design/theme';
import { radius, size, space } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { keyExists, t as tr } from '@/i18n/store';
import { useT } from '@/i18n/useT';
import type { CapturedPage } from '@/store/session';

import { maskAround, maskFromDrag } from './masks';

export interface MaskEditorProps {
  page: CapturedPage;
  pageNumber: number;
  visible: boolean;
  onChange(masks: MaskRect[]): void;
  onClose(): void;
}

type Point = { x: number; y: number };

/** "Box {i} added, covering part of page {n}" (PRODUCT_SPEC S5); the key is pending WP0 (CL line),
 *  so the announcement is skipped rather than reading a raw key. */
export const MASK_ADDED_KEY = 'a11y.mask_added';

function announceMask(i: number, n: number) {
  if (!keyExists(MASK_ADDED_KEY)) return;
  try {
    AccessibilityInfo.announceForAccessibility(tr(MASK_ADDED_KEY, { i, n }));
  } catch {
    // best-effort
  }
}

export function MaskEditor({ page, pageNumber, visible, onChange, onClose }: MaskEditorProps) {
  const t = useT();
  const add = (m: MaskRect) => {
    onChange([...page.masks, m]);
    announceMask(page.masks.length + 1, pageNumber);
  };
  const { colors } = useTheme();
  const dir = useDirection();
  const [box, setBox] = useState({ width: 0, height: 0 });
  const [draft, setDraft] = useState<MaskRect | null>(null);
  const start = useRef<{ local: Point; page: Point } | null>(null);
  const aspect = page.width && page.height ? page.height / page.width : 1.294;

  const endPoint = (e: GestureResponderEvent): Point | null => {
    const s = start.current;
    if (!s) return null;
    return { x: s.local.x + (e.nativeEvent.pageX - s.page.x), y: s.local.y + (e.nativeEvent.pageY - s.page.y) };
  };

  // Plain responder props (no PanResponder object): handlers run only in events.
  const responder = {
    onStartShouldSetResponder: () => true,
    onMoveShouldSetResponder: () => true,
    onResponderGrant: (e: GestureResponderEvent) => {
      start.current = {
        local: { x: e.nativeEvent.locationX, y: e.nativeEvent.locationY },
        page: { x: e.nativeEvent.pageX, y: e.nativeEvent.pageY },
      };
    },
    onResponderMove: (e: GestureResponderEvent) => {
      const s = start.current;
      const end = endPoint(e);
      if (s && end) setDraft(maskFromDrag(s.local, end, box));
    },
    onResponderRelease: (e: GestureResponderEvent) => {
      const s = start.current;
      const end = endPoint(e);
      start.current = null;
      setDraft(null);
      if (!s || !end) return;
      const moved = Math.abs(end.x - s.local.x) > 8 || Math.abs(end.y - s.local.y) > 8;
      const dragged = moved ? maskFromDrag(s.local, end, box) : null;
      const next =
        dragged ?? (box.width > 0 && box.height > 0 ? maskAround({ x: s.local.x / box.width, y: s.local.y / box.height }) : null);
      if (next) add(next);
    },
    onResponderTerminate: () => {
      start.current = null;
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

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose} transparent={false}>
      <ScrollView style={{ backgroundColor: colors.background }} contentContainerStyle={styles.body}>
        <Heading level={1}>{t('review.hide_parts')}</Heading>
        <AppText>{t('review.hide_tip')}</AppText>
        <AppText color="textMuted">{t('review.hide_note_receipt')}</AppText>
        <View
          onLayout={onLayout}
          style={[styles.canvas, { height: box.height || 320, borderColor: colors.border }]}
          accessibilityLabel={`${pageNumber}. ${t('review.hide_tip')}`}
          {...responder}>
          <View pointerEvents="none" style={StyleSheet.absoluteFill}>
            <Image source={{ uri: page.uri }} contentFit="fill" style={StyleSheet.absoluteFill} />
          </View>
          {page.masks.map((m, i) => (
            <View key={`m-${i}`} pointerEvents="none" style={[styles.mask, rectStyle(m)]} />
          ))}
          {draft ? <View pointerEvents="none" style={[styles.draft, { borderColor: colors.focus }, rectStyle(draft)]} /> : null}
        </View>
        {page.masks.map((m, i) => (
          <View key={`row-${i}`} style={[styles.row, { flexDirection: dir.row, borderColor: colors.divider }]}>
            <View style={[styles.swatch]} />
            <View style={styles.flex}>
              <AppText>{`${t('review.hide_parts')} ${i + 1}`}</AppText>
            </View>
            <Pressable
              role="button"
              accessibilityLabel={`${t('review.remove')} ${i + 1}`}
              hitSlop={size.hitSlop}
              onPress={() => onChange(page.masks.filter((_, j) => j !== i))}
              style={[styles.remove, { borderColor: colors.danger }]}>
              <AppText color="danger" weight="bold">
                {t('review.remove')}
              </AppText>
            </Pressable>
          </View>
        ))}
        <BigButton
          label={t('review.hide_parts')}
          icon="lock"
          variant="secondary"
          size={56}
          onPress={() => add(maskAround({ x: 0.5, y: 0.5 }))}
        />
        <BigButton label={t('capture.done')} icon="check" variant="primary" size={72} onPress={onClose} />
      </ScrollView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  body: {
    padding: space.screenGutter,
    gap: space.lg,
    maxWidth: 720,
    width: '100%',
    alignSelf: 'center',
  },
  canvas: {
    width: '100%',
    borderWidth: 1,
    overflow: 'hidden',
    // The page is never mirrored in RTL.
    direction: 'ltr',
  },
  mask: {
    position: 'absolute',
    backgroundColor: '#000000',
  },
  draft: {
    position: 'absolute',
    backgroundColor: 'rgba(0,0,0,0.6)',
    borderWidth: 2,
  },
  row: {
    alignItems: 'center',
    gap: space.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingTop: space.sm,
  },
  swatch: {
    width: 24,
    height: 12,
    backgroundColor: '#000000',
  },
  flex: {
    flex: 1,
  },
  remove: {
    minHeight: size.minTouch,
    justifyContent: 'center',
    borderWidth: 2,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
  },
});
