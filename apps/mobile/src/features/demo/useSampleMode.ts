// Sample mode (PRODUCT_SPEC §12.1, S17 item 7): the Settings toggle, forced ON when the server
// runs the mock provider (`settings.sample_forced`), and ON at first launch in judging builds via
// `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE=true` (store/settings default).

import { useSession } from '@/store/session';
import { useSettings } from '@/store/settings';

export interface SampleModeState {
  enabled: boolean;
  set(on: boolean): void;
  /** True when the server only has sample papers (`provider == mock`); the toggle is locked on. */
  forced: boolean;
}

export function useSampleMode(): SampleModeState {
  const sampleMode = useSettings((s) => s.sampleMode);
  const setSetting = useSettings((s) => s.set);
  const forced = useSession((s) => s.serverConfig?.provider === 'mock');
  return {
    enabled: sampleMode || forced,
    forced,
    set: (on: boolean) => setSetting('sampleMode', on),
  };
}
