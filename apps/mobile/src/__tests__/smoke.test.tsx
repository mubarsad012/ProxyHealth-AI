import { render } from '@testing-library/react-native';
import { Text, View } from 'react-native';

function Hello({ name }: { name: string }) {
  return (
    <View accessibilityRole="summary">
      <Text>Hello, {name}</Text>
    </View>
  );
}

describe('test stack smoke', () => {
  it('renders a React Native component under jest-expo', async () => {
    const { getByText } = await render(<Hello name="ProxyHealth" />);
    expect(getByText('Hello, ProxyHealth')).toBeTruthy();
  });
});
