// Settings switch rows (D-28, PRODUCT_SPEC S17): the whole ≥ 56 pt row is one `role="switch"`
// control, so the label is tappable and the target is not RN-web's fixed 40×20 px input; the drawn
// switch keeps ≥ 3:1 against the page in every palette (WCAG 1.4.11).

import { fireEvent, render } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';

import { SwitchRow } from '@/design/components/SettingsRows';
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

describe('SwitchRow', () => {
  it('is one switch control: the label row toggles, reports checked, and is ≥ 56 pt tall', async () => {
    const onChange = jest.fn();
    const { getByTestId, getByText, getByRole } = await render(
      <SwitchRow label="High contrast" value={false} onChange={onChange} explanation="Stronger colours" testID="hc" />,
    );
    const row = getByTestId('hc');
    expect(getByRole('switch', { name: 'High contrast' })).toBe(row);
    expect(row.props.accessibilityState).toEqual({ checked: false, disabled: false });

    await fireEvent.press(getByText('High contrast'));
    expect(onChange).toHaveBeenLastCalledWith(true);
    await fireEvent.press(row);
    expect(onChange).toHaveBeenCalledTimes(2);

    const style = StyleSheet.flatten(typeof row.props.style === 'function' ? row.props.style({ pressed: false }) : row.props.style);
    expect(style.minHeight).toBeGreaterThanOrEqual(56);
  });

  it('turns off when checked', async () => {
    const onChange = jest.fn();
    const on = await render(<SwitchRow label="Sample mode" value onChange={onChange} testID="s" />);
    await fireEvent.press(on.getByTestId('s'));
    expect(onChange).toHaveBeenLastCalledWith(false);
  });

  it('does nothing while disabled', async () => {
    const off = jest.fn();
    const disabled = await render(<SwitchRow label="Lock screen" value={false} onChange={off} disabled testID="d" />);
    await fireEvent.press(disabled.getByTestId('d'));
    expect(off).not.toHaveBeenCalled();
    expect(disabled.getByTestId('d').props.accessibilityState).toEqual({ checked: false, disabled: true });
  });

  it('the drawn switch has ≥ 3:1 against the page in every palette, on and off', () => {
    for (const p of Object.values(palette)) {
      expect(contrast(p.border, p.background)).toBeGreaterThanOrEqual(3); // off: track outline
      expect(contrast(p.border, p.surface)).toBeGreaterThanOrEqual(3); // off: thumb on track
      expect(contrast(p.primary, p.background)).toBeGreaterThanOrEqual(3); // on: track
      expect(contrast(p.onPrimary, p.primary)).toBeGreaterThanOrEqual(3); // on: thumb on track
    }
  });
});
