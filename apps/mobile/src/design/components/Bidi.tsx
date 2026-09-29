// Bidi isolation for verbatim values (D-26, PRODUCT_SPEC §5.2 rule 2): dates, case/receipt numbers,
// amounts, phones, URLs, agency names and quotes keep their own direction inside RTL (or LTR) text.
// Native: Unicode isolates LRI/RLI/FSI … PDI around the content. Web: a span with `dir` (the HTML UA
// stylesheet gives `[dir]` `unicode-bidi: isolate`; `global.css` repeats it for `[data-bidi]`).
// Digits are never localized or reversed here.

import { Children, type ReactNode } from 'react';
import { Platform, Text, type TextStyle } from 'react-native';

import { AppText, type TextVariant } from '@/design/components/Text';

export type BidiDir = 'ltr' | 'rtl' | 'auto';

export const LRI = '⁦';
export const RLI = '⁧';
export const FSI = '⁨';
export const PDI = '⁩';

export function isolateChar(dir: BidiDir): string {
  return dir === 'ltr' ? LRI : dir === 'rtl' ? RLI : FSI;
}

/** Wrap a plain string in isolate marks (native path; exported for tests and TTS-free copies). */
export function isolate(text: string, dir: BidiDir = 'ltr'): string {
  return `${isolateChar(dir)}${text}${PDI}`;
}

/** Strip isolate marks (clipboard / quick-sheet text). */
export function stripIsolates(text: string): string {
  return text.replace(/[⁦-⁩]/g, '');
}

/** Web DOM attributes for an isolated span (RN types do not declare `dir`/`data-*`). */
export function bidiWebProps(dir: BidiDir): Record<string, string> {
  return { dir, 'data-bidi': dir };
}

export interface BidiProps {
  children: ReactNode;
  dir?: BidiDir;
  /** When set, renders as a standalone styled text (not nested in another text). */
  variant?: TextVariant;
  weight?: 'regular' | 'bold';
  style?: TextStyle;
  accessibilityLabel?: string;
}

export function Bidi({ children, dir = 'ltr', variant, weight, style, accessibilityLabel }: BidiProps) {
  const isWeb = Platform.OS === 'web';
  const parts = Children.toArray(children);
  const allText = parts.every((p) => typeof p === 'string' || typeof p === 'number');
  const content: ReactNode = isWeb
    ? children
    : allText
      ? isolate(parts.map(String).join(''), dir)
      : [isolateChar(dir), ...parts, PDI];
  // An inline `direction` from the surrounding pack would beat the `dir` attribute on web.
  const dirStyle: TextStyle = dir === 'auto' ? {} : { writingDirection: dir };
  const webProps = isWeb
    ? ({ ...bidiWebProps(dir), style: [{ unicodeBidi: 'isolate' } as TextStyle, dirStyle, style] } as object)
    : { style: [dirStyle, style] };
  if (variant) {
    return (
      <AppText variant={variant} weight={weight} align="auto" accessibilityLabel={accessibilityLabel} {...webProps}>
        {content}
      </AppText>
    );
  }
  return (
    <Text accessibilityLabel={accessibilityLabel} {...webProps}>
      {content}
    </Text>
  );
}
