# ProxyHealth AI — mobile app (`apps/mobile`)

One Expo codebase for iOS, Android and the web: Expo SDK 57, React Native 0.86, React 19, TypeScript 6, Expo Router with routes in `src/app/`. The product, screens and copy are specified in [`docs/PRODUCT_SPEC.md`](../../docs/PRODUCT_SPEC.md); the API it talks to is [`docs/API_CONTRACT.md`](../../docs/API_CONTRACT.md). Read [`AGENTS.md`](AGENTS.md) before touching Expo APIs — they change every SDK, so check the SDK 57 docs, not memory.

## Run it

From the repo root, with zero API keys:

```sh
make dev          # mock API on :8000 + this app on http://localhost:8081
```

Or this app alone against an API you already run:

```sh
export PATH="$HOME/.local/node/bin:$PATH"     # Node 24 on this Mac
cd apps/mobile
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo start --web
```

No Xcode on this Mac, so no iOS simulator (`npx expo run:ios` cannot work). Test on the web, or on a phone: Expo Go for quick smoke checks (it shows generic permission strings and has no notifications/RTL-restart support), an EAS development build for real testing (`npx eas-cli@latest build --profile development --platform android`).

## Checks (keep them green)

```sh
npx tsc --noEmit                    # TypeScript 6: add @types to tsconfig "types" explicitly
npx jest --maxWorkers=2             # jest-expo; @testing-library/react-native v14: render() is async
npx expo lint
npx expo config --type prebuild > /dev/null     # after any app.json change: plugins, icons, strings resolve
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000 npx expo export --platform web --clear   # → dist/
```

`scripts/ci.sh` at the repo root runs these after the API checks. CI (fresh checkout) first runs `npm ci --legacy-peer-deps` and `npx expo customize tsconfig.json` (creates the git-ignored `expo-env.d.ts` for typed routes). Never run `npm install` / `npx expo install` while other agents work; `--legacy-peer-deps` is needed because `openapi-typescript` pins TypeScript 5.

## Configuration

| Variable (baked in at build/export) | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | `http://127.0.0.1:8000` | API base URL; set per profile in `eas.json` (HTTPS for `preview`/`production`) |
| `EXPO_PUBLIC_APP_TOKEN` | empty | sent as `X-App-Token` when set (public by nature, not a secret) |
| `EXPO_PUBLIC_APP_ENV` | `development` | the developer section in Settings shows unless `production` |
| `EXPO_PUBLIC_DEFAULT_SAMPLE_MODE` | `false` | start in sample mode (the `demo` build) |

No secrets ever live in the app. Always export with `--clear` when you change `EXPO_PUBLIC_API_URL` (Metro caches inlined env values).

`app.json` holds the store configuration (name "ProxyHealth AI", slug/scheme `proxyhealth`, placeholder ids `org.proxyhealth.app` — open question Q4), permission strings on the camera/image-picker plugins (mirrored in `ios.infoPlist`), `android.blockedPermissions` (no `READ_MEDIA_*`), `android.allowBackup: false`, `ios.privacyManifests`, `ios.config.usesNonExemptEncryption: false`, the `expo-notifications` channel and icon, fonts, and `locales/` for iOS permission-string translations. `eas.json` has the `development`, `preview`, `demo` and `production` profiles — see [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) §3. Never create or edit `ios/` or `android/`; native configuration goes through `app.json` and config plugins.

## Artwork

`assets/images/` holds the app mark — a sheet of paper with a folded corner and a speech bubble with a check, in the brand colours of `src/design/tokens.ts`. Every file is drawn by the repo-root `scripts/make_artwork.py` (Pillow, 4× supersampled; kept out of `assets/` so it never ships in the app bundle):

| File | Size | Notes |
|---|---|---|
| `icon.png` | 1024×1024 | opaque (iOS rejects transparency), full-bleed `#0B4F8A` |
| `android-icon-foreground.png` | 1024×1024 | transparent; the mark stays inside the central 66 % circle |
| `android-icon-background.png` | 1024×1024 | solid `#0B4F8A` (also `adaptiveIcon.backgroundColor`) |
| `android-icon-monochrome.png` | 1024×1024 | one colour on transparent (Android 13 themed icons) |
| `splash-icon.png` | 1024×1024 | transparent; rounded blue tile so the white paper shows on the white splash |
| `favicon.png` | 48×48 | simplified lines; Expo converts it to `favicon.ico` on export |
| `notification-icon.png` | 96×96 | white glyph on transparent (Android status bar) |
| `../expo.icon/` | — | iOS 26 layered icon: the same mark (`Assets/proxyhealth-mark.png`) over the brand fill |

Redraw after a change: `apps/api/.venv/bin/python scripts/make_artwork.py` (from the repo root), then `npx expo config --type prebuild > /dev/null`.

## Web extras

`public/` is copied into the web export: `public/privacy/index.html` is the public privacy policy served at `/privacy` (`PRIVACY_POLICY_URL`). It is plain HTML with `lang`/`dir`, readable without JavaScript, and checked by `apps/api/tests/unit/test_privacy_claims.py` (no forbidden phrases, the in-app notice sentences verbatim, the current consent version). Hosting and response headers: [`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md) §2.

## Layout

```
src/app/        routes only (onboarding/, (tabs)/, scan/, result/[id]/, papers/, troubleshoot, reminders, emergency)
src/api/        schema.d.ts (generated from ../api/openapi.json — do not edit), types, client, errors, offline
src/design/     tokens.ts ("Big Calm"), theme, components
src/i18n/       packs/ (synced from the API — do not edit), direction, digits, fonts, useT
src/storage/    vault (native sqlite + files | web memory / opt-in IndexedDB), kv, secure, wipe
src/features/   onboarding, scan, analysis, chat, clerk, help, vault, reminders, quicksheet, troubleshoot,
                speech, demo, feedback, emergency, settings
src/lib/ src/store/ src/hooks/
assets/         images/ (art), expo.icon/, fonts/ (Noto, OFL), fixtures/ and resources/ (synced)
locales/        iOS permission strings per language (synced)
public/         privacy/index.html
```

Generated files (`src/api/schema.d.ts`, `src/i18n/packs/*`, `src/i18n/languages.ts`, `assets/fixtures/**`, `assets/resources/**`, `assets/fonts/**`, `locales/*.json`) are written only by their generators (`scripts/gen-types.sh`, `apps/api/scripts/sync_to_mobile.py`).
