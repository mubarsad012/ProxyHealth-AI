// S16 screenshot preview with "Hide parts" (PRODUCT_SPEC S16, same rules as S5 / D-19). The
// preview shows the picked screenshot with its black boxes; "Hide parts" opens S5's `MaskEditor`
// (imported as is) on a `CapturedPage` view of the screenshot. How the boxes are sent lives in
// `masks.ts` (web: burned on a canvas; native: `masks[]` burned by the server).

import { useState } from 'react';
import { Image, StyleSheet, View } from 'react-native';

import type { MaskRect } from '@/api/types';
import { BigButton } from '@/design/components';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';
import { MaskEditor } from '@/features/scan/MaskEditor';
import { useT } from '@/i18n/useT';

import { screenshotPage } from './masks';
import type { Screenshot } from './pick';

export interface ScreenshotPreviewProps {
  shot: Screenshot;
  masks: MaskRect[];
  onChangeMasks(masks: MaskRect[]): void;
  disabled?: boolean;
}

export function ScreenshotPreview({ shot, masks, onChangeMasks, disabled }: ScreenshotPreviewProps) {
  const t = useT();
  const { colors } = useTheme();
  const [editing, setEditing] = useState(false);
  const aspectRatio = shot.width && shot.height ? shot.width / shot.height : 0.6;
  return (
    <View style={styles.wrap} testID="troubleshoot-preview">
      <View style={[styles.frame, { borderColor: colors.border, aspectRatio }]}>
        <Image source={{ uri: shot.uri }} accessibilityIgnoresInvertColors style={StyleSheet.absoluteFill} resizeMode="stretch" />
        {masks.map((m, i) => (
          <View
            key={`mask-${i}`}
            testID={`troubleshoot-mask-${i}`}
            pointerEvents="none"
            style={[
              styles.mask,
              {
                left: `${m.x0 * 100}%`,
                top: `${m.y0 * 100}%`,
                width: `${(m.x1 - m.x0) * 100}%`,
                height: `${(m.y1 - m.y0) * 100}%`,
              },
            ]}
          />
        ))}
      </View>
      <BigButton
        label={t('review.hide_parts')}
        icon="lock"
        variant="secondary"
        size={56}
        disabled={disabled}
        onPress={() => setEditing(true)}
        accessibilityHint={t('review.hide_tip')}
        testID="troubleshoot-hide-parts"
      />
      {editing ? (
        <MaskEditor
          page={screenshotPage(shot, masks)}
          pageNumber={1}
          visible
          onChange={onChangeMasks}
          onClose={() => setEditing(false)}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: space.sm,
    alignItems: 'center',
  },
  frame: {
    width: '60%',
    maxWidth: 280,
    borderWidth: 1,
    borderRadius: radius.sm,
    overflow: 'hidden',
    // The screenshot is never mirrored in RTL (the boxes are in image coordinates).
    direction: 'ltr',
  },
  mask: {
    position: 'absolute',
    backgroundColor: '#000000',
  },
});
