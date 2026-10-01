// SpeakButton with no voice for the language (D-26, PRODUCT_SPEC J-A step 9): nothing is spoken and
// the tap is not met with silence — the button announces `tts.no_voice` and carries it as its label.
// (`tts.no_voice` is a new en.json key added by the merge step; `t()` returns the key until then,
// and both sides of these assertions go through `t()`.)

import { fireEvent, render, waitFor } from '@testing-library/react-native';
import * as Speech from 'expo-speech';
import { AccessibilityInfo } from 'react-native';

import { SpeakButton } from '@/design/components/SpeakButton';
import { t } from '@/i18n/store';
import { resetVoicesForTests, type Voice } from '@/lib/tts';

jest.mock('@react-native-async-storage/async-storage', () =>
  jest.requireActual('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);

const EN_ONLY = [{ identifier: 'samantha', name: 'Samantha', language: 'en-US', quality: Speech.VoiceQuality.Default } as Voice];

afterEach(() => {
  jest.restoreAllMocks();
  resetVoicesForTests();
});

it('Dari on a phone with only an English voice: says so instead of reading it in English', async () => {
  jest.spyOn(Speech, 'getAvailableVoicesAsync').mockResolvedValue(EN_ONLY);
  const spoken = jest.spyOn(Speech, 'speak').mockImplementation(() => undefined);
  const announce = jest.spyOn(AccessibilityInfo, 'announceForAccessibility').mockImplementation(() => undefined);
  const onResolved = jest.fn();
  const { getByLabelText } = await render(
    <SpeakButton text="اگر کسی در خطر است، به 911 زنگ بزنید." lang="prs" onResolved={onResolved} />,
  );
  await fireEvent.press(getByLabelText(t('btn.read_aloud')));
  const line = t('tts.no_voice', { language: 'دری' });
  await waitFor(() => expect(getByLabelText(line)).toBeTruthy());
  expect(announce).toHaveBeenCalledWith(line);
  expect(spoken).not.toHaveBeenCalled();
  expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ noVoice: true, voice: null }));
});
