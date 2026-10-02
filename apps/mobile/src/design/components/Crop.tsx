// Highlighted crop of a page image around a quote's bbox (D-09, PRODUCT_SPEC S7 Card 2). bbox is
// normalised `[x0, y0, x1, y1]` in 0..1 of the page image (API_CONTRACT TextBlock). Page images
// and crops are never mirrored in RTL. Without a bbox the full page is shown; without an image
// the quote text alone is shown. `accessibilityLabel` is the quote (WCAG 1.1.1).

import { Image } from 'expo-image';
// Never cache user page images to disk: expo-image defaults to cachePolicy 'disk' (privacy, D-22).
import { useState } from 'react';
import { type LayoutChangeEvent, StyleSheet, View } from 'react-native';

import { Bidi } from '@/design/components/Bidi';
import { useTheme } from '@/design/theme';
import { radius, space } from '@/design/tokens';

export interface CropProps {
  pageImageUri: string | null;
  bbox: number[] | null;
  quote: string;
  /** Pixel width/height of the page image the bbox refers to (for the aspect ratio). */
  width?: number | null;
  height?: number | null;
}

const PAD = 0.02;

export interface CropGeometry {
  imageWidth: number;
  imageHeight: number;
  left: number;
  top: number;
  viewportHeight: number;
  highlight: { left: number; top: number; width: number; height: number };
}

/** Pure layout math (exported for tests): place the image so the padded bbox fills the viewport. */
export function cropGeometry(bbox: number[], containerWidth: number, aspect: number): CropGeometry {
  const [x0, y0, x1, y1] = bbox.map((v) => Math.min(1, Math.max(0, v)));
  const cx0 = Math.max(0, Math.min(x0, x1) - PAD);
  const cy0 = Math.max(0, Math.min(y0, y1) - PAD);
  const cx1 = Math.min(1, Math.max(x0, x1) + PAD);
  const cy1 = Math.min(1, Math.max(y0, y1) + PAD);
  const bw = Math.max(0.05, cx1 - cx0);
  const imageWidth = containerWidth / bw;
  const imageHeight = imageWidth * aspect;
  const viewportHeight = Math.min(240, Math.max(48, (cy1 - cy0) * imageHeight));
  return {
    imageWidth,
    imageHeight,
    left: -cx0 * imageWidth,
    top: -cy0 * imageHeight,
    viewportHeight,
    highlight: {
      left: (Math.min(x0, x1) - cx0) * imageWidth,
      top: (Math.min(y0, y1) - cy0) * imageHeight,
      width: Math.abs(x1 - x0) * imageWidth,
      height: Math.abs(y1 - y0) * imageHeight,
    },
  };
}

export function Crop({ pageImageUri, bbox, quote, width, height }: CropProps) {
  const { colors } = useTheme();
  const [containerWidth, setContainerWidth] = useState(0);
  const aspect = width && height ? height / width : 1.294; // US Letter when unknown
  const onLayout = (e: LayoutChangeEvent) => setContainerWidth(e.nativeEvent.layout.width);

  if (!pageImageUri) {
    return (
      <View style={[styles.quoteOnly, { borderColor: colors.divider }]}>
        <Bidi dir="auto" variant="caption">
          {quote}
        </Bidi>
      </View>
    );
  }

  if (!bbox || bbox.length !== 4) {
    return (
      <Image
        source={{ uri: pageImageUri }}
        cachePolicy="memory"
        accessibilityLabel={quote}
        contentFit="contain"
        style={[styles.full, { aspectRatio: 1 / aspect, borderColor: colors.divider }]}
      />
    );
  }

  const g = containerWidth > 0 ? cropGeometry(bbox, containerWidth, aspect) : null;
  return (
    <View
      accessible
      role="img"
      accessibilityLabel={quote}
      onLayout={onLayout}
      style={[styles.viewport, { height: g?.viewportHeight ?? 96, borderColor: colors.divider }]}>
      {g ? (
        <>
          <Image
            source={{ uri: pageImageUri }}
            cachePolicy="memory"
            contentFit="fill"
            style={{ position: 'absolute', left: g.left, top: g.top, width: g.imageWidth, height: g.imageHeight }}
          />
          <View
            pointerEvents="none"
            style={[
              styles.highlight,
              {
                left: g.highlight.left,
                top: g.highlight.top,
                width: g.highlight.width,
                height: g.highlight.height,
                borderColor: colors.focus,
              },
            ]}
          />
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  viewport: {
    width: '100%',
    overflow: 'hidden',
    borderRadius: radius.sm,
    borderWidth: 1,
    // Never mirrored: the crop keeps the page's own orientation in RTL.
    direction: 'ltr',
  },
  highlight: {
    position: 'absolute',
    borderWidth: 3,
    borderRadius: radius.sm,
    backgroundColor: 'rgba(255, 214, 0, 0.18)',
  },
  full: {
    width: '100%',
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  quoteOnly: {
    padding: space.md,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
});
