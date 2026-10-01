// Store-facing native config (app.json) — checks a device build cannot be run for here:
// - COMPLIANCE_PRIVACY §12 / §12.1, RUNBOOK: the Android manifest must not carry the Expo template's
//   READ/WRITE_EXTERNAL_STORAGE or SYSTEM_ALERT_WINDOW, nor media/microphone permissions, so each is
//   removed with `blockedPermissions` (`tools:node="remove"` in the merged manifest). The
//   introspected list (`npx expo config --type introspect`) is then CAMERA, INTERNET, VIBRATE, plus
//   POST_NOTIFICATIONS from expo-notifications at build time.
// - WCAG 2.2 AA 1.3.4 Orientation (COMPLIANCE_PRIVACY §15): the app is not locked to portrait.

import appJson from '../../app.json';

type AppJson = {
  expo: {
    orientation?: string;
    android?: { blockedPermissions?: string[]; permissions?: string[] };
  };
};

const config = (appJson as AppJson).expo;

const MUST_BE_BLOCKED = [
  'android.permission.READ_EXTERNAL_STORAGE',
  'android.permission.WRITE_EXTERNAL_STORAGE',
  'android.permission.SYSTEM_ALERT_WINDOW',
  'android.permission.READ_MEDIA_IMAGES',
  'android.permission.READ_MEDIA_VIDEO',
  'android.permission.RECORD_AUDIO',
];

describe('app.json', () => {
  it('blocks every Android permission COMPLIANCE §12 says must not appear', () => {
    const blocked = config.android?.blockedPermissions ?? [];
    for (const p of MUST_BE_BLOCKED) expect(blocked).toContain(p);
    for (const p of MUST_BE_BLOCKED) expect(config.android?.permissions ?? []).not.toContain(p);
  });

  it('does not lock phones to one orientation (WCAG 1.3.4)', () => {
    expect(config.orientation ?? 'default').toBe('default');
  });
});
