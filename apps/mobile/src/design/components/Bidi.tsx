// Bidi isolation for verbatim values (D-26, PRODUCT_SPEC §5.2 rule 2): dates, case/receipt numbers,
// amounts, phones, URLs, agency names and quotes keep their own direction inside RTL (or LTR) text.
// Native: Unicode isolates LRI/RLI … PDI around the content. Web: a span with `dir` (the HTML UA
// stylesheet gives `[dir]` `unicode-bidi: isolate`; `global.css` repeats it for `[data-bidi]`).
// `dir="auto"` (sender names, quotes, terms as printed) resolves to the direction of the text's
// first strong character — else the layout's — and sets it explicitly: on web an inline
// `direction` inherited from `AppText` would otherwise beat the `dir="auto"` attribute, so an
// English quote inside a Dari card would still show its full stop on the left. Content that is
// not plain text keeps FSI (native) / `dir="auto"` (web). Digits are never localized or reversed.
// The string helpers live in `@/i18n/bidi` (pure, shared with `useT` and the quick sheet).

import { Children, type ReactNode } from 'react';
import { Platform, Text, type TextStyle } from 'react-native';

import { AppText, type TextVariant } from '@/design/components/Text';
import { type BidiDir, isolate, isolateChar, PDI, resolveAuto } from '@/i18n/bidi';
import { useDirection } from '@/i18n/direction';

export {
  FSI,
  firstStrongDirection,
  isolate,
  isolateChar,
  isolateForLayout,
  LRI,
  PDI,
  RLI,
  stripIsolates,
  strongDirection,
} from '@/i18n/bidi';
export type { BidiDir } from '@/i18n/bidi';

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
  const layout = useDirection().dir;
  const isWeb = Platform.OS === 'web';
  const parts = Children.toArray(children);
  const allText = parts.every((p) => typeof p === 'string' || typeof p === 'number');
  const text = allText ? parts.map(String).join('') : '';
  // `auto` over plain text becomes a concrete direction; over elements it stays FSI / dir="auto".
  const resolved: BidiDir = dir === 'auto' && allText ? resolveAuto(text, layout) : dir;
  const content: ReactNode = isWeb
    ? children
    : allText
      ? isolate(text, resolved)
      : [isolateChar(resolved), ...parts, PDI];
  // An inline `direction` from the surrounding pack would beat the `dir` attribute on web.
  const dirStyle: TextStyle = resolved === 'auto' ? {} : { writingDirection: resolved };
  const webProps = isWeb
    ? ({ ...bidiWebProps(resolved), style: [{ unicodeBidi: 'isolate' } as TextStyle, dirStyle, style] } as object)
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
