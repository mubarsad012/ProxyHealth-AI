// Text primitives (D-28, PRODUCT_SPEC §5.1–§5.2). Every visible string goes through `AppText` so the
// pack's font family (`font_hint`), the script line-height multiplier (Nastaliq 2.0), the in-app
// text-size factor, the palette colour and the direction (`textAlign`/`writingDirection`) are
// applied in one place. `allowFontScaling` stays on; no fixed heights; text always wraps.

import type { ReactNode } from 'react';
import { Platform, Text, type TextProps, type TextStyle } from 'react-native';

import { useTheme } from '@/design/theme';
import { type Palette, type as typeScale } from '@/design/tokens';
import { useDirection } from '@/i18n/direction';
import { fontFamilyFor, lineHeightFor } from '@/i18n/fonts';
import { usePackMeta } from '@/i18n/useT';

export type TextVariant = keyof typeof typeScale.size;
export type TextColor = keyof Pick<
  Palette,
  'text' | 'textMuted' | 'primary' | 'onPrimary' | 'onSecondary' | 'danger' | 'onDanger' | 'success' | 'warning' | 'link'
>;

export interface AppTextProps extends Omit<TextProps, 'children'> {
  children?: ReactNode;
  variant?: TextVariant;
  weight?: 'regular' | 'bold';
  color?: TextColor;
  /** Explicit colour (urgency tokens); wins over `color`. */
  colorValue?: string;
  /** Alignment override; default follows the pack direction. `'auto'` leaves it to the platform. */
  align?: 'start' | 'end' | 'center' | 'auto';
  /** BCP-47 tag of this text when it differs from the UI pack (source quotes, language chips). */
  lang?: string;
  /** Font hint override (e.g. a language chip rendered in its own script). */
  fontHint?: string | null;
}

/** Web-only DOM attributes that RN's types do not declare (`lang`, `dir`). */
export function webLangProps(lang?: string, dir?: 'ltr' | 'rtl' | 'auto'): Record<string, string> {
  if (Platform.OS !== 'web') return {};
  const out: Record<string, string> = {};
  if (lang) out.lang = lang;
  if (dir) out.dir = dir;
  return out;
}

export function useTextStyle(
  variant: TextVariant = 'body',
  weight: 'regular' | 'bold' = 'regular',
  fontHintOverride?: string | null,
): TextStyle {
  const { textFactor } = useTheme();
  const meta = usePackMeta();
  const hint = fontHintOverride === undefined ? meta.fontHint : fontHintOverride;
  const size = Math.max(typeScale.minBody, Math.round(typeScale.size[variant] * textFactor));
  const baseLine = Math.round(typeScale.lineHeight[variant] * textFactor);
  const family = fontFamilyFor(hint, weight);
  return {
    fontSize: size,
    lineHeight: lineHeightFor(hint, baseLine),
    // With a bundled family the weight is in the file; the system font needs fontWeight.
    ...(family ? { fontFamily: family } : { fontWeight: weight === 'bold' ? '700' : '400' }),
  };
}

export function AppText({
  children,
  variant = 'body',
  weight = 'regular',
  color = 'text',
  colorValue,
  align,
  lang,
  fontHint,
  style,
  ...rest
}: AppTextProps) {
  const theme = useTheme();
  const dir = useDirection();
  const base = useTextStyle(variant, weight, fontHint);
  const textAlign: TextStyle['textAlign'] =
    align === 'center'
      ? 'center'
      : align === 'auto'
        ? 'auto'
        : align === 'end'
          ? dir.textAlign === 'left'
            ? 'right'
            : 'left'
          : dir.textAlign;
  return (
    <Text
      allowFontScaling
      {...rest}
      {...(lang ? { accessibilityLanguage: lang } : null)}
      {...webLangProps(lang)}
      style={[
        base,
        { color: colorValue ?? theme.colors[color], textAlign, writingDirection: dir.writingDirection },
        style,
      ]}>
      {children}
    </Text>
  );
}

export interface HeadingProps extends AppTextProps {
  /** Heading level for screen readers (web `aria-level`). */
  level?: 1 | 2 | 3;
}

export function Heading({ level = 2, variant, weight = 'bold', ...rest }: HeadingProps) {
  const v: TextVariant = variant ?? (level === 1 ? 'heading' : level === 2 ? 'title' : 'bodyLarge');
  // `aria-level` is a react-native-web prop that RN's types do not declare.
  const levelProp = (Platform.OS === 'web' ? { 'aria-level': level } : {}) as object;
  return <AppText role="heading" {...levelProp} variant={v} weight={weight} {...rest} />;
}
