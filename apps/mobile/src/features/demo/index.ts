// Seam stub (BUILD_PLAN §4.2 / §5.0). Owner after M0: WP6. Keep every export name and signature.

import type { ReactElement } from 'react';

import type { DemoFixture } from '@/api/types';
import type { CapturedPage } from '@/store/session';

export interface SamplePickerProps {
  onPick(sample: DemoFixture, pages: CapturedPage[]): void;
}

/** Sample-paper picker (from /v1/demo/fixtures or the bundled manifest). Day-0 stub renders nothing. */
export function SamplePicker(_props: SamplePickerProps): ReactElement | null {
  return null;
}

/** Sample mode flag (persisted in settings by WP6). Day-0 stub: off, setter ignored. */
export function useSampleMode(): { enabled: boolean; set(on: boolean): void } {
  return { enabled: false, set: () => {} };
}

/** "This is a sample paper" banner. Day-0 stub renders nothing. */
export function SampleBanner(): ReactElement | null {
  return null;
}
