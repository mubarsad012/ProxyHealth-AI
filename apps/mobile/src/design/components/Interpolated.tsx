// Render a pack string whose placeholders must stay LTR-isolated (PRODUCT_SPEC §5.5: `{date}` inside
// `<Bidi dir="ltr">`). The template is the untranslated-placeholder string from `t(key)`.

import { Fragment, type ReactNode } from 'react';

import { Bidi } from '@/design/components/Bidi';
import { AppText, type AppTextProps } from '@/design/components/Text';

const PLACEHOLDER = /\{([a-zA-Z0-9_]+)\}/g;

export interface TemplatePart {
  kind: 'text' | 'var';
  value: string;
  name?: string;
}

/** Split a template into literal text and filled placeholders (unknown placeholders stay literal). */
export function splitTemplate(template: string, vars: Record<string, string | number>): TemplatePart[] {
  const parts: TemplatePart[] = [];
  let last = 0;
  for (const m of template.matchAll(PLACEHOLDER)) {
    const idx = m.index ?? 0;
    if (idx > last) parts.push({ kind: 'text', value: template.slice(last, idx) });
    const name = m[1];
    const v = vars[name];
    parts.push(v === undefined ? { kind: 'text', value: m[0] } : { kind: 'var', value: String(v), name });
    last = idx + m[0].length;
  }
  if (last < template.length) parts.push({ kind: 'text', value: template.slice(last) });
  return parts;
}

export interface InterpolatedProps extends Omit<AppTextProps, 'children'> {
  template: string;
  vars: Record<string, string | number>;
  /** Placeholders rendered inside `<Bidi dir="ltr">` (dates, amounts, numbers, names as printed). */
  ltrKeys?: readonly string[];
}

export function Interpolated({ template, vars, ltrKeys = ['date'], ...textProps }: InterpolatedProps) {
  const parts = splitTemplate(template, vars);
  const nodes: ReactNode[] = parts.map((p, i) =>
    p.kind === 'var' && p.name && ltrKeys.includes(p.name) ? (
      <Bidi key={i} dir="ltr">
        {p.value}
      </Bidi>
    ) : (
      <Fragment key={i}>{p.value}</Fragment>
    ),
  );
  return <AppText {...textProps}>{nodes}</AppText>;
}
