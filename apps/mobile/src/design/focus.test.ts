// Web focus ring (WCAG 2.4.7 / 1.4.11, COMPLIANCE_PRIVACY §15): the `:focus-visible` outline takes
// the active palette's `focus` token (a CSS variable ThemeProvider sets), with a dark-scheme default
// before the app starts, and every palette's focus colour keeps ≥ 3:1 against all its backgrounds.
// The fixed light-palette #0B4F8A ring was 1.6–2.2:1 on the dark palette.

import { applyWebFocusColor } from '@/design/theme';
import { palette } from '@/design/tokens';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

function luminance(hex: string): number {
  const n = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map((i) => {
    const c = Number.parseInt(n.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

function globalCss(): string {
  const fs = jest.requireActual<{ readFileSync(path: string, enc: 'utf8'): string }>('fs');
  const testPath = expect.getState().testPath ?? '';
  return fs.readFileSync(testPath.replace(/design[\\/]focus\.test\.ts$/, 'global.css'), 'utf8');
}

describe('focus ring', () => {
  it.each(Object.entries(palette))('%s: focus colour ≥ 3:1 on background, surface and raised surface', (_name, p) => {
    for (const bg of [p.background, p.surface, p.surfaceRaised]) {
      expect(contrast(p.focus, bg)).toBeGreaterThanOrEqual(3);
    }
  });

  it('global.css draws the ring from --ph-focus with light and dark defaults from the tokens', () => {
    const css = globalCss().toLowerCase();
    const rule = /:focus-visible\s*\{([^}]*)\}/.exec(css)?.[1] ?? '';
    expect(rule).toMatch(/outline:\s*3px solid var\(--ph-focus/);
    expect(css).toContain(`--ph-focus: ${palette.light.focus.toLowerCase()}`);
    const dark = /@media \(prefers-color-scheme: dark\)\s*\{([\s\S]*?)\}\s*\}/.exec(css)?.[1] ?? '';
    expect(dark).toContain(`--ph-focus: ${palette.dark.focus.toLowerCase()}`);
  });

  it('ThemeProvider pushes the active palette focus colour onto <html>', () => {
    const setProperty = jest.fn();
    applyWebFocusColor(palette.dark.focus, { documentElement: { style: { setProperty } } });
    expect(setProperty).toHaveBeenCalledWith('--ph-focus', '#9CC4F5');
    expect(() => applyWebFocusColor('#000000', undefined)).not.toThrow();
  });
});
