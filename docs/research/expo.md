# Research: expo

_Verified by a research agent on 2026-09-23 against official sources. Input to the ProxyHealth design; not a spec._

# Expo cross-platform research (verified 2026-09-23 against docs.expo.dev, expo.dev/changelog, reactnative.dev, registry.npmjs.org, and github.com/expo/expo `sdk-57` branch)

## 1. SDK version and project creation

**Current stable: Expo SDK 57.** `expo@57.0.24` is the npm `latest` dist-tag (published 2026-09-18). SDK 57 was released June 30, 2026 (SDK 56 on May 21, 2026). **SDK 58 is in beta** since Sept 15, 2026 (`expo@next` = `58.0.0-preview.6`); it ships React Native 0.88 RC and goes stable "shortly after" RN 0.88 ships (beta lasts 3–4 weeks).

- SDK 57 pins **React Native 0.86.3** and **React 19.2.3** (`packages/expo/bundledNativeModules.json` on the `sdk-57` branch; docs list "React Native version 0.86", "React 19.2.3", Node ≥ 22.13.x). Note npm `react-native@latest` is 0.87.1 — do NOT install that; `npx expo install` pins 0.86.3.
- **New Architecture:** "SDK 55 and later run entirely on the New Architecture. The New Architecture is always enabled and cannot be disabled." `newArchEnabled` is irrelevant on SDK 57.

**Create command (TypeScript + Expo Router):**
```sh
npx create-expo-app@latest my-app            # default template = Expo Router + TypeScript
# equivalent explicit form:
npx create-expo-app@latest my-app --template default
```
Official template table (docs.expo.dev/more/create-expo/):
| template | what you get |
|---|---|
| `default` | "Designed to build multi-screen apps. Includes … Expo Router library and TypeScript configuration enabled." |
| `tabs` | "Installs and configures file-based routing with Expo Router and TypeScript enabled." |
| `blank-typescript` | "A Blank template with TypeScript enabled." — **no Expo Router** (`main: index.ts`) |
| `blank` | JS, no navigation |
| `bare-minimum` | blank + generated `android/` and `ios/` dirs |

What the SDK 57 `default` template (57.0.26) actually contains (from GitHub `templates/expo-template-default`): `main: "expo-router/entry"`, routes in **`src/app/`** (`_layout.tsx`, `index.tsx`, `explore.tsx`), tabs implemented with **`NativeTabs` from `expo-router/unstable-native-tabs`**, `app.json` has `"web": {"output": "static"}`, `"experiments": {"typedRoutes": true, "reactCompiler": true}`, `userInterfaceStyle: "automatic"`, deps include `expo-image`, `expo-router`, `@expo/ui`, `expo-glass-effect`, `expo-symbols`, `react-native-web ~0.21.0`, `react-dom 19.2.3`, devDeps `typescript ~6.0.3`, `@types/react ~19.2.2`. tsconfig: `extends expo/tsconfig.base`, `strict: true`, `paths {"@/*": ["./src/*"]}`, `include [..., ".expo/types/**/*.ts", "expo-env.d.ts"]`. The `tabs` template is a leaner Router+TS setup (JS `Tabs`, `web.output: static`, `typedRoutes: true`, no `@expo/ui`/glass/react-compiler).

Other flags: `--yes`, `--no-install`, `--no-agents-md` (skips AGENTS.md/CLAUDE.md), `--example <expo/examples name>`. Try SDK 58 beta with `npx create-expo-app@latest --template default@next`; upgrade existing with `npx expo install expo@next --fix` (stable upgrade: `npx expo install expo@^57.0.0 --fix`).

## 2. Capability packages (all versions = SDK 57 line unless noted; always install with `npx expo install <pkg>` so versions match the SDK)

### Camera capture and photo library
**`expo-camera` 57.0.5** — Android, iOS, Web, Expo Go. `npx expo install expo-camera`
```tsx
import { CameraView, CameraType, useCameraPermissions } from 'expo-camera';
const [facing, setFacing] = useState<CameraType>('back');
const [permission, requestPermission] = useCameraPermissions();
// <CameraView ref={ref} style={{flex:1}} facing={facing} />
const photo = await ref.current?.takePictureAsync({ quality: 0.8, base64: true, exif: false, skipProcessing: false });
// -> CameraCapturedPicture { uri, width, height, base64?, exif?, format }
```
Web: "Image URIs are always returned as base64 strings because local file system paths are unavailable in the browser" (`uri` === `base64` data). Cross-origin iframes need `allow="microphone; camera;"`. Config plugin:
```json
["expo-camera", { "cameraPermission": "Allow $(PRODUCT_NAME) to access your camera", "microphonePermission": "Allow $(PRODUCT_NAME) to access your microphone" }]
```

**`expo-image-picker` 57.0.19** — Android, iOS, Web, Expo Go. `npx expo install expo-image-picker`
```ts
import * as ImagePicker from 'expo-image-picker';
const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.8, allowsEditing: true, aspect: [4,3], base64: false, allowsMultipleSelection: false });
const cam = await ImagePicker.launchCameraAsync({ mediaTypes: ['images'], quality: 0.8 });
if (!res.canceled) { const a = res.assets[0]; /* uri, width, height, base64?, fileName?, mimeType?, file? (web-only File) */ }
```
`mediaTypes` is now an array (`['images','videos','livePhotos']`); the `MediaTypeOptions` enum is deprecated. Web gotchas: both launchers "must be called immediately in a user interaction like a button press, otherwise the browser will block the request"; "The `cancelled` event will not be returned in the browser"; `requestCameraPermissionsAsync()` and `requestMediaLibraryPermissionsAsync()` "do nothing on web"; the web asset carries a `file: File` you can put in `FormData`. Plugin: `["expo-image-picker", {"photosPermission": "...", "cameraPermission": "...", "microphonePermission": false}]` (`false` blocks the Android permission).

**Recommendation:** use `expo-image-picker` for "take a photo or pick one" (system UI, simplest, works on web via `<input type=file capture>`); use `expo-camera` only when you need an in-app live preview/custom capture UI.

### Image manipulation / compression
**`expo-image-manipulator` 57.0.19** — Android, iOS, tvOS, Web, Expo Go. `npx expo install expo-image-manipulator`
```ts
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
const ctx = ImageManipulator.manipulate(uri).resize({ width: 1280 });   // also .crop(rect) .rotate(deg) .flip('horizontal') .extent({...})
const img = await ctx.renderAsync();
const out = await img.saveAsync({ compress: 0.7, format: SaveFormat.JPEG, base64: false }); // { uri, width, height, base64? }
// or hook: const ctx = useImageManipulator(uri)
```
`manipulateAsync()` is deprecated in favor of this context API.

### Text-to-speech
**`expo-speech` 57.0.3** — Android, iOS, **Web**, Expo Go. `npx expo install expo-speech`
```ts
import * as Speech from 'expo-speech';
const voices = await Speech.getAvailableVoicesAsync(); // Voice { identifier, name, language, quality: 'Default'|'Enhanced' }; on web WebVoice adds voiceURI
Speech.speak(text, { language: 'ar-SA' /* BCP 47 */, voice: voices[0]?.identifier, rate: 1.0, pitch: 1.0, volume: 1.0,
  onStart, onDone, onStopped, onError /* Android, iOS only */, onBoundary });
Speech.stop(); await Speech.isSpeakingAsync(); Speech.pause(); Speech.resume(); // pause/resume: iOS + web only
Speech.maxSpeechInputLength // platform-dependent; Number.MAX_VALUE on iOS
```
Gotchas: iOS "won't produce sound if the device is in silent mode"; Android has no pause/resume; text longer than `maxSpeechInputLength` fails. Web is backed by the browser SpeechSynthesis API (callbacks receive `SpeechSynthesisEvent`), so available voices/languages depend on the browser/OS.

### PDF generation and sharing
**`expo-print` 57.0.2** — Android, iOS, Web, Expo Go. `npx expo install expo-print`
**`expo-sharing` 57.0.21** — Android, iOS, Web, Expo Go. `npx expo install expo-sharing`
```ts
import * as Print from 'expo-print';
import { shareAsync, isAvailableAsync } from 'expo-sharing';
const { uri, numberOfPages } = await Print.printToFileAsync({ html, width: 612, height: 792, base64: false, margins: { top: 40, bottom: 40, left: 40, right: 40 } });
await shareAsync(uri, { UTI: '.pdf', mimeType: 'application/pdf', dialogTitle: 'Share report' });
await Print.printAsync({ html }); // opens native print UI
```
Web behavior (verbatim): `printToFileAsync` — "On Web this method opens the print dialog" (no PDF file is produced); `printAsync` — "On web this prints the HTML from the page." Sharing on web uses the Web Share API: "very limited browser support", "only available on web when the page is served over https", and "Sharing local files by URI works on Android and iOS, but not on web." Always gate with `await isAvailableAsync()`. iOS: local image assets are not supported inside `printToFileAsync` HTML (WKWebView) — embed images as base64 data URIs.

### Secure storage
**`expo-secure-store` 57.0.4** — Android, iOS, tvOS, Expo Go. **No web support** (platform list excludes web; importing on web gives no working implementation). `npx expo install expo-secure-store`
```ts
import * as SecureStore from 'expo-secure-store';
await SecureStore.setItemAsync('token', value, { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK, requireAuthentication: false });
const v = await SecureStore.getItemAsync('token'); await SecureStore.deleteItemAsync('token');
SecureStore.getItem('k'); SecureStore.setItem('k','v'); // sync variants (block JS thread)
await SecureStore.isAvailableAsync(); SecureStore.canUseBiometricAuthentication();
```
Gotchas: "Large payloads can be rejected by the underlying platform. Historically, some iOS releases refused values above roughly 2048 bytes"; iOS keychain data persists across uninstall/reinstall of same bundle ID; Android Auto Backup must exclude SecureStore data; `requireAuthentication` not supported in Expo Go (needs `faceIDPermission` plugin option in a dev build). **Web fallback is your responsibility**: branch on `Platform.OS === 'web'` (e.g. keep tokens in memory / httpOnly cookies, or a `localStorage` wrapper with the understanding that it is not encrypted).

### Local persistence
**`expo-sqlite` 57.0.3** — Android, iOS, macOS, tvOS, **Web (alpha)**, Expo Go. `npx expo install expo-sqlite`
```tsx
import * as SQLite from 'expo-sqlite';
const db = await SQLite.openDatabaseAsync('app.db');
await db.execAsync(`PRAGMA journal_mode = 'wal'; CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY NOT NULL, body TEXT NOT NULL);`);
await db.runAsync('INSERT INTO notes (body) VALUES (?)', body);
const rows = await db.getAllAsync<{id:number; body:string}>('SELECT * FROM notes');
const one = await db.getFirstAsync('SELECT * FROM notes WHERE id = ?', id);
await db.withTransactionAsync(async () => { /* ... */ });
// React: <SQLiteProvider databaseName="app.db" onInit={migrateDbIfNeeded}><Main/></SQLiteProvider>; const db = useSQLiteContext();
// migrations: read `PRAGMA user_version`, run, then `PRAGMA user_version = N`
// key-value drop-in for AsyncStorage:
import Storage from 'expo-sqlite/kv-store'; await Storage.setItem('k','v'); Storage.getItemSync('k');
```
Web setup (required): `metro.config.js` → `config.resolver.assetExts.push('wasm')`; serve with headers `Cross-Origin-Embedder-Policy: credentialless` and `Cross-Origin-Opener-Policy: same-origin` (on EAS Hosting set via `["expo-router", {"headers": {...}}]` plugin). "Web support is in alpha and may be unstable."

**AsyncStorage** — `npx expo install @react-native-async-storage/async-storage` (Android, iOS, macOS, tvOS, Web, Expo Go; "asynchronous, unencrypted, persistent, key-value"). **Expo SDK 57 pins `2.2.0`** via `bundledNativeModules.json`, while npm `latest` is `3.1.1` (published 2026-05-29). Stick with what `npx expo install` picks. For a new app prefer `expo-sqlite` (+ `expo-sqlite/kv-store` for simple KV) so you have one storage story; use AsyncStorage only if you need a zero-setup web path without the COOP/COEP headers.

### File system
**`expo-file-system` 57.0.7** — Android, iOS, tvOS, Expo Go. **Web not supported.** `npx expo install expo-file-system`
```ts
import { File, Directory, Paths } from 'expo-file-system';
const dir = new Directory(Paths.document, 'reports'); if (!dir.exists) dir.create();
const f = new File(dir, 'report.txt'); f.create(); f.write('hello');       // SDK 58: write() becomes async; writeSync() keeps sync behavior
const txt = await f.text(); const b64 = await f.base64(); const bytes = await f.bytes(); f.uri; f.exists;
const pdf = await File.downloadFileAsync('https://example.com/a.pdf', new Directory(Paths.cache, 'pdfs'));
// legacy API still available: import * as FileSystem from 'expo-file-system/legacy';
```
`Paths.document` = "safe from being deleted by the system"; `Paths.cache` = can be purged under low storage. On web, use Blob/URL.createObjectURL or upload directly with the `file`/`base64` fields the pickers return.

### Localization and RTL
**`expo-localization` 57.0.2** — Android, iOS, tvOS, Web, Expo Go. `npx expo install expo-localization`
```ts
import { getLocales, getCalendars, useLocales } from 'expo-localization';
const { languageTag, languageCode, regionCode, textDirection /* 'ltr'|'rtl' */, currencyCode /* null on web */, measurementSystem /* null on web */ } = getLocales()[0];
```
Config plugin (build-time):
```json
["expo-localization", { "supportsRTL": true, "forcesRTL": false, "supportedLocales": { "ios": ["en", "ar"], "android": ["en", "ar"] } }]
```
"RTL support is enabled by default. Layout direction follows React Native's `I18nManager`… On iOS, the device language must also be one of your app's supported locales, declared with the `supportedLocales` option." Set `supportsRTL: false` to opt out; `forcesRTL: true` for RTL-only apps/testing. Runtime toggle (native only):
```ts
import { I18nManager, Platform } from 'react-native'; import * as Updates from 'expo-updates';
if (shouldBeRTL !== I18nManager.isRTL && Platform.OS !== 'web') { I18nManager.allowRTL(shouldBeRTL); I18nManager.forceRTL(shouldBeRTL); Updates.reloadAsync(); }
```
RN docs: `allowRTL()`/`forceRTL()` changes "take effect on the next application start, not immediately" and persist. **Web:** `I18nManager` does not flip layout; instead set the DOM direction: `<View dir={getLocales()[0].textDirection || 'ltr'}>…</View>` ("`textDirection` is not available on Firefox and older browser versions"). SDK 58 change: on iOS "RTL is no longer force-enabled from the device locale with `supportsRTL`; layout direction follows `I18nManager`." Recommended i18n libs in the guide: i18n-js (demo), Lingui, react-i18next, Intlayer, fbtee. `expo.locales` in app.json localizes permission prompts.

### Haptics
**`expo-haptics` 57.0.3** — Android, iOS, Web. `npx expo install expo-haptics`
```ts
import * as Haptics from 'expo-haptics';
await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);          // Light|Medium|Heavy|Rigid|Soft
await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
await Haptics.selectionAsync();
await Haptics.performAndroidHapticsAsync(Haptics.AndroidHaptics.Confirm); // Android-only, preferred over Vibrator
```
Web: needs browser vibration API + hardware; "some browsers may ignore vibration in certain contexts". Safe to call everywhere (no-ops silently). Adds Android `VIBRATE` permission automatically.

### Images
**`expo-image` 57.0.5** — Android, iOS, tvOS, Web, Expo Go. `npx expo install expo-image`
```tsx
import { Image } from 'expo-image';
<Image source={{ uri }} style={{ width: 200, height: 200 }} contentFit="cover" placeholder={{ blurhash }} transition={200} cachePolicy="memory-disk" recyclingKey={id} alt="Photo of …" />
await Image.prefetch([url]); await Image.clearMemoryCache();
```
Web: renders `<img>`; `responsivePolicy` (`static|initial|live`) drives `srcset/sizes`; `loading="lazy"` supported; `alt` maps to the HTML alt attribute.

### Document picker (PDFs)
**`expo-document-picker` 57.0.2** — Android, iOS, Web, Expo Go. `npx expo install expo-document-picker`
```ts
import * as DocumentPicker from 'expo-document-picker';
const r = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', multiple: false, copyToCacheDirectory: true, base64: false /* web only */ });
if (!r.canceled) { const { uri, name, size, mimeType, file /* web File */ } = r.assets[0]; }
```
Web: only after user activation; cancel not reliably reported; result includes `File` (and `base64` if requested). iCloud: `["expo-document-picker", {"iCloudContainerEnvironment": "Production"}]`.

### Clipboard
**`expo-clipboard` 57.0.2** — Android, iOS, Web, Expo Go. `npx expo install expo-clipboard`
```ts
import * as Clipboard from 'expo-clipboard';
await Clipboard.setStringAsync(text); const s = await Clipboard.getStringAsync(); await Clipboard.hasStringAsync();
await Clipboard.setImageAsync(base64Png); const sub = Clipboard.addClipboardListener(({ contentTypes }) => {});
```
Web: uses the AsyncClipboard API "which might behave differently between browsers or not be fully supported"; reading prompts the user for clipboard-read permission; a WebKit bug "makes this API unusable in asynchronous code" (call directly inside the click handler, not after an `await`).

### Speech-to-text (community)
**`expo-speech-recognition` 57.1.0** (jamsch; SDK-aligned dist-tags, e.g. `sdk-56` → 56.0.4). `npx expo install expo-speech-recognition`
- **Requires a development build — not available in Expo Go.** iOS 17+, Android 12+ (13+ for extra features). **Web: Chrome, Safari 16+, Edge via Web Speech API; not Firefox/Brave.**
```json
["expo-speech-recognition", { "microphonePermission": "Allow $(PRODUCT_NAME) to use the microphone.", "speechRecognitionPermission": "Allow $(PRODUCT_NAME) to use speech recognition.", "androidSpeechServicePackages": ["com.google.android.googlequicksearchbox"] }]
```
```ts
import { ExpoSpeechRecognitionModule, useSpeechRecognitionEvent } from 'expo-speech-recognition';
useSpeechRecognitionEvent('result', e => setTranscript(e.results[0]?.transcript));
useSpeechRecognitionEvent('end', () => setListening(false)); useSpeechRecognitionEvent('error', e => console.warn(e.error, e.message));
const p = await ExpoSpeechRecognitionModule.requestPermissionsAsync();
ExpoSpeechRecognitionModule.start({ lang: 'en-US', interimResults: true, continuous: false, requiresOnDeviceRecognition: false });
ExpoSpeechRecognitionModule.stop();
```

## 3. Expo Router

- **Version:** `expo-router@57.0.22` (versions are SDK-aligned since SDK 55; SDK 54 was 6.0.x). Manual install: `npx expo install expo-router react-native-safe-area-context react-native-screens expo-linking expo-constants expo-status-bar`, set `"main": "expo-router/entry"`, add `"scheme"` in app.json, plugin `"expo-router"`.
- **Conventions:** routes live in `app/` or `src/app/` ("The `src/app` directory takes higher precedence… Only the `src/app` directory will be used if you have both"). `_layout.tsx` (layout, not a page), `index.tsx` (default route), `[param].tsx` (dynamic), `[...rest].tsx` (catch-all), `(group)/` (grouping without affecting URL), `+not-found.tsx`, `+html.tsx` (web HTML shell), `+native-intent.tsx` (unmatched deep links), `+middleware.ts` (pre-render code; stable in SDK 58), `name+api.ts` (API route, needs `web.output: server`).
- **Tabs (JS, works on web):**
```tsx
// src/app/_layout.tsx
import { Stack } from 'expo-router';
export default function Root() { return <Stack><Stack.Screen name="(tabs)" options={{ headerShown: false }} /></Stack>; }
// src/app/(tabs)/_layout.tsx
import { Tabs } from 'expo-router';
export default function TabLayout() {
  return (<Tabs screenOptions={{ tabBarActiveTintColor: 'blue' }}>
    <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: ({ color }) => <FontAwesome size={28} name="home" color={color} /> }} />
    <Tabs.Screen name="settings" options={{ title: 'Settings' }} />
  </Tabs>);
}
```
  **Native tabs:** `import { NativeTabs } from 'expo-router/unstable-native-tabs'` on SDK 54–57 (what the default template uses); `expo-router/native-tabs` (stable) on SDK 58+. `<NativeTabs><NativeTabs.Trigger name="index"><NativeTabs.Trigger.Label>Home</NativeTabs.Trigger.Label><NativeTabs.Trigger.Icon sf="house.fill" md="home" /></NativeTabs.Trigger></NativeTabs>`. On web native tabs "fall back to a basic implementation" — the docs recommend a `_layout.web.tsx` using `expo-router/ui` headless tabs.
- **Typed routes:** `"experiments": {"typedRoutes": true}` (already on in default/tabs templates); Expo CLI generates git-ignored `expo-env.d.ts`; `<Link href="/about" />`, `<Link href={{ pathname: '/user/[id]', params: { id: 1 } }} />`, `router.push('/about')` are type-checked. Keep `".expo/types/**/*.ts"` and `"expo-env.d.ts"` in tsconfig `include`.
- **Web output & export:** `web.output` ∈ `single` (SPA, **default**), `static` (HTML per route; templates set this), `server` (static HTML + API routes; default in SDK 58 when API routes are used). Export: `npx expo export --platform web` (alias `-p web`) → `dist/` (with server output: `dist/server` + `dist/client`); `public/` is copied in. Test locally: `npx serve dist`.
- **Hosting:**
  - EAS Hosting: `npm i -g eas-cli && eas login`, then `npx expo export --platform web && eas deploy` (first run picks a subdomain → `https://my-app.expo.app`, previews `https://my-app--<id>.expo.app`; `eas deploy --prod` for production). Runs on Cloudflare Workers ("partial Node.js support"); supports API routes with `server` output. Free plan: 100,000 requests/mo, 1,000,000 CPU-ms, 1 GB storage, 5 aliases; custom domains are paid-plan only.
  - Vercel: `vercel.json` `{"buildCommand": "expo export -p web", "outputDirectory": "dist", "devCommand": "expo", "cleanUrls": true, "framework": null, "rewrites": [{"source": "/:path*", "destination": "/"}]}` then `vercel`. (Drop the rewrite for `static` output; use `expo-server/adapter/vercel` for `server` — experimental.)
  - Netlify: `public/_redirects` with `/*    /index.html   200` for SPA; `netlify deploy --dir dist`.
  - GitHub Pages: `experiments.baseUrl: "/repo-name"`, `gh-pages --nojekyll -d dist`.

## 4. EAS Build & Submit, store config, Expo Go

- **Pricing (expo.dev/pricing):** Free $0 — "15 Android and 15 iOS builds" per month, low-priority queue, 45-minute build timeout, 1 concurrency, medium workers only, EAS Update 1K MAU, EAS Submit included, EAS Hosting limits above. Starter $19/mo + usage; Production $199/mo + usage; usage builds $1 Android / $2 iOS (medium). Paid plans: 2-hour timeout.
- **iOS without a Mac:** EAS Build runs "on macOS runners hosted in Expo's macOS cloud"; "EAS Submit works on macOS, Linux, and Windows, so you don't need a Mac to ship iOS builds." You still need an Apple Developer Program membership ($99/yr) and a Google Play Developer account ($25 one-time).
- **Commands:**
```sh
npm install --global eas-cli && eas login
eas build:configure                              # creates eas.json, prompts for bundleIdentifier / package
eas build --platform ios --profile development   # dev client build (no Xcode needed)
eas build --platform all --profile production    # store binaries (.ipa / .aab)
eas build --platform all --profile production --auto-submit
eas submit --platform ios      # needs ascAppId (App Store Connect "Apple ID"), Apple ID or ASC API key
eas submit --platform android  # needs Google service account JSON; .aab; first release goes to internal track
```
- **eas.json reference shape:**
```json
{ "cli": { "appVersionSource": "remote" },
  "build": { "development": { "developmentClient": true, "distribution": "internal" },
             "preview": { "distribution": "internal" },
             "production": { "autoIncrement": true } },
  "submit": { "production": { "ios": { "ascAppId": "1234567890", "appleId": "you@example.com", "appleTeamId": "AB12XYZ34S" },
                              "android": { "serviceAccountKeyPath": "./google-service-account.json", "track": "internal" } } } }
```
  `appVersionSource: "remote"` is "the recommended behavior from EAS CLI version 12.0.0" — EAS then owns `ios.buildNumber`/`android.versionCode` increments.
- **app.json fields for stores:**
```json
{ "expo": {
  "name": "My App", "slug": "my-app", "version": "1.0.0", "scheme": "myapp", "userInterfaceStyle": "automatic",
  "ios": { "bundleIdentifier": "com.example.myapp", "buildNumber": "1", "supportsTablet": true,
           "infoPlist": { "NSCameraUsageDescription": "…", "NSPhotoLibraryUsageDescription": "…", "NSMicrophoneUsageDescription": "…", "NSSpeechRecognitionUsageDescription": "…" },
           "privacyManifests": { "NSPrivacyAccessedAPITypes": [ { "NSPrivacyAccessedAPIType": "NSPrivacyAccessedAPICategoryUserDefaults", "NSPrivacyAccessedAPITypeReasons": ["CA92.1"] } ] } },
  "android": { "package": "com.example.myapp", "versionCode": 1, "permissions": ["android.permission.RECORD_AUDIO"], "blockedPermissions": [] },
  "locales": { "ar": "./locales/ar.json" },
  "web": { "output": "static" },
  "plugins": [ "expo-router", ["expo-camera", {…}], ["expo-image-picker", {…}], ["expo-localization", {…}], ["expo-speech-recognition", {…}] ],
  "experiments": { "typedRoutes": true } } }
```
  Prefer each library's config-plugin permission strings; `ios.infoPlist` is the escape hatch. "Changes to the Info.plist cannot be updated over-the-air, they will only be deployed when you submit a new native binary." Apple privacy manifests: Expo's guide says "Apple does not correctly parse all the PrivacyInfo files included by static CocoaPods dependencies (such as Expo SDK packages…)", so declare required-reason API categories yourself in `ios.privacyManifests` (check each package's docs or Apple's rejection email).
- **Expo Go vs development builds:** Expo Go "is a playground for students and learners… cannot use third-party libraries that require custom native code" and "is limited and not useful for building production-grade projects." Config-plugin permission strings, `expo-speech-recognition`, SecureStore `requireAuthentication`, and any custom native module need a **development build** (`npx expo install expo-dev-client`, then `eas build --profile development` or `npx expo run:ios|android`). Store status: as of May 2026 the App Store Expo Go supports **SDK 54**; SDK 55/57 versions were "still waiting on approval"; SDK 57/58 Expo Go is available only via Expo CLI (Android devices, iOS simulators) or `eas go` (builds your own Expo Go to TestFlight, requires Apple Developer account). Since SDK 56 `create-expo-app` prompts to choose App-Store-compatible vs latest SDK.

## 5. Accessibility (React Native) and theming

- Props (View/Text/Pressable): `accessible`, `accessibilityLabel`, `accessibilityHint`, `accessibilityRole` (`button|link|header|image|imagebutton|search|text|checkbox|radio|switch|tab|tablist|menu|progressbar|adjustable|alert|summary|toolbar|…`), `accessibilityState={{disabled, selected, checked|'mixed', busy, expanded}}`, `accessibilityValue={{min,max,now,text}}`, `accessibilityLiveRegion="polite|assertive"` (Android), `importantForAccessibility` (Android), `accessibilityLanguage` (iOS), `accessibilityActions` + `onAccessibilityAction`. Web-friendly aliases: `role="button|heading|img|link|…"` (takes priority), `aria-label`, `aria-hidden`, `aria-live`, `aria-checked`, `aria-selected`, `aria-valuenow`, etc.
- `AccessibilityInfo`: `isScreenReaderEnabled()`, `isReduceMotionEnabled()`, `announceForAccessibility(msg)`, `announceForAccessibilityWithOptions(msg, {queue})` (iOS), `sendAccessibilityEvent(ref, 'focus')` (replaces deprecated `setAccessibilityFocus`), contrast/vision queries `isBoldTextEnabled()` (iOS), `isHighTextContrastEnabled()` (Android), `isDarkerSystemColorsEnabled()` (iOS "Increase Contrast"), `isInvertColorsEnabled()`, `isGrayscaleEnabled()`, `isReduceTransparencyEnabled()`; events `screenReaderChanged`, `reduceMotionChanged`, `boldTextChanged`, `invertColorsChanged`, `highTextContrastChanged` (Android) via `addEventListener`.
- Large text: `Text` `allowFontScaling` defaults to `true` (respects system Text Size); cap with `maxFontSizeMultiplier` (`0` = no max; `>=1` cap); iOS `dynamicTypeRamp="body|headline|title1|largeTitle|…"`; `adjustsFontSizeToFit` + `minimumFontScale` for shrinking; `PixelRatio.getFontScale()` returns the user's font-size multiplier (Android Settings > Display > Font size; iOS Text Size / Larger Text) for layout math.
- Touch targets: RN docs do **not** state a minimum size; they provide `hitSlop` on `Pressable` ("additional distance outside of element in which a press can be detected") and `pressRetentionOffset`. The 44×44 pt (Apple HIG) / 48×48 dp (Material) minimums come from platform guidelines, not RN docs — implement with `minWidth/minHeight: 44` plus `hitSlop`.
- Dark mode: `"userInterfaceStyle": "automatic"` in app.json (template default); `useColorScheme()` / `Appearance.getColorScheme()` + `Appearance.addChangeListener` from `react-native`; on Android dev builds `expo-system-ui` must be installed or `userInterfaceStyle` is ignored (the default template already includes it). Expo Router exports `ThemeProvider`, `DarkTheme`, `DefaultTheme` (used by the template). No dedicated Expo high-contrast helper exists — combine `useColorScheme()` with `AccessibilityInfo.isHighTextContrastEnabled()`/`isDarkerSystemColorsEnabled()` and `isBoldTextEnabled()` to pick a high-contrast palette.

## 6. Testing and type-check

```sh
npx expo install jest-expo jest @types/jest --dev            # Windows: npx expo install jest-expo jest @types/jest "--" --dev
npx expo install @testing-library/react-native --dev
npm i -D test-renderer                                       # RNTL 14 peer dep (^1.0.0); Expo docs omit it
```
package.json:
```json
{ "scripts": { "test": "jest --watchAll", "typecheck": "tsc" },
  "jest": { "preset": "jest-expo" } }
```
tsconfig: add `"types": ["jest"]` under `compilerOptions` (per Expo docs). `jest-expo` presets: `jest-expo` (default, iOS env), `jest-expo/ios`, `jest-expo/android`, `jest-expo/web`, `jest-expo/node`, `jest-expo/universal` (runs all; snapshots saved as `.snap.ios`, `.snap.web`, …; platform-specific tests via `-test.ios.tsx`, `-test.web.tsx`). `jest-expo@57.0.5` peers: `@react-native/jest-preset ^0.86.3`. If Jest hits untransformed ESM in node_modules, add the documented `transformIgnorePatterns` (`node_modules/(?!((jest-)?react-native|@react-native(-community)?)|expo(nent)?|@expo(nent)?/.*|@expo-google-fonts/.*|react-navigation|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg)`).

Example test (`__tests__/home-screen-test.tsx`; `-test.tsx` suffix is auto-detected):
```tsx
import { render, screen } from '@testing-library/react-native';
import HomeScreen from '@/app/index';
test('renders welcome', async () => { render(<HomeScreen />); expect(screen.getByText('Welcome!')).toBeOnTheScreen(); });
```
RNTL 14.0.1 requires `react >= 19`, `react-native >= 0.78`, `jest >= 29`, and `test-renderer ^1.0.0`; Expo docs: "`@testing-library/react-native` replaces the deprecated `react-test-renderer` because `react-test-renderer` does not support React 19 and above." Matchers are built in (`toBeOnTheScreen`, etc.) once you import from the library.

**Type-check:** Expo docs say run `tsc` from the project root (`npm run tsc` in their example, which assumes a script). `expo/tsconfig.base` already sets `"noEmit": true`, so `npx tsc` and `npx tsc --noEmit` are equivalent; add `"typecheck": "tsc --noEmit"` to scripts and run `npm run typecheck`. Start the dev server once (`npx expo start`) or run `npx expo customize tsconfig.json` first so `expo-env.d.ts` (typed routes) exists, otherwise route-typed `href`s fail type-check. Template uses TypeScript `~6.0.3`, `strict: true`, `moduleResolution: bundler`, `customConditions: ["react-native"]`. Lint: `npx expo lint`.

## Warnings for builders

- Do not install `react-native@latest` (0.87.1) or `@react-native-async-storage/async-storage@latest` (3.1.1) by hand: Expo SDK 57 pins react-native 0.86.3 and async-storage 2.2.0. Always add packages with `npx expo install <pkg>` and fix drift with `npx expo install --fix`.
- `--template blank-typescript` does NOT include Expo Router (entry is index.ts). Use the `default` template (Router + TS + native tabs + typed routes) or `tabs` (Router + TS, lighter) for a file-based-routing app.
- The SDK 57 default template imports `NativeTabs` from `expo-router/unstable-native-tabs`; that path becomes `expo-router/native-tabs` in SDK 58. Native tabs only fall back to a basic layout on web — add a `_layout.web.tsx` with `expo-router/ui` (or use JS `Tabs` everywhere) if web parity matters.
- SDK 58 (beta now, stable within weeks) changes `File.write()` to async (use `File.writeSync()` for the old behavior), removes expo-sqlite libSQL, makes `web.output: server` the default when API routes are used, and changes iOS RTL to follow I18nManager. If you start on 57 today, plan a 58 upgrade before store submission (iOS 27 scene-based lifecycle support lands there).
- Web is NOT supported by expo-secure-store or the new expo-file-system API (neither lists web). Branch on `Platform.OS === 'web'`: keep secrets out of storage or use an explicitly unencrypted fallback, and handle files via the `file`/`base64` fields that expo-image-picker / expo-document-picker return on web.
- PDF export on web does not produce a file: `Print.printToFileAsync` "opens the print dialog" on web, and `Sharing.shareAsync` cannot share local URIs on web and needs HTTPS + Web Share API support. Use a browser-side approach (e.g. print-to-PDF via the dialog, or a JS PDF library / server render) for web.
- expo-sqlite on web is alpha and requires COEP `credentialless` + COOP `same-origin` headers and a `wasm` Metro asset extension; static hosts (Vercel/Netlify) need explicit header config, and these headers can break third-party embeds. Consider AsyncStorage or IndexedDB for the web tier if you cannot control headers.
- On web, expo-image-picker, expo-document-picker and expo-clipboard reads must run synchronously inside the user gesture handler (no awaits before the call); cancel events are not reported by browsers, so never block UI waiting for `canceled`.
- expo-speech-recognition (community, jamsch) requires a development build — it will not load in Expo Go — and only works on Chrome/Safari 16+/Edge on web (not Firefox/Brave); iOS 17+/Android 12+ only. Add NSSpeechRecognitionUsageDescription via its config plugin.
- expo-speech on iOS is silent when the ringer switch is on silent; Android lacks pause/resume; voice availability (especially for non-English/RTL languages) varies by device/browser — query `getAvailableVoicesAsync()` and fall back to `language` only.
- Expo Go on the App Store was still at SDK 54 as of May 2026; SDK 57/58 Expo Go is only available via Expo CLI (Android/iOS simulator) or `eas go` (TestFlight, needs Apple Developer account). Build a development build (`eas build --profile development`) from day one — it is also required for config-plugin permission strings and any custom native module.
- EAS Free plan limits: 15 iOS + 15 Android builds per month, low-priority queue, 45-minute timeout, 1 concurrent build, no large workers. Budget builds (use `--profile preview` internal builds sparingly) or expect to move to Starter ($19/mo).
- Store submission prerequisites are external: Apple Developer Program ($99/yr, app record created in App Store Connect for `ascAppId`) and Google Play Developer ($25 one-time, service-account JSON, first Android release lands on the internal track and store listing must be completed manually). EAS Submit uploads binaries only — no metadata/screenshots.
- Permission strings and privacy manifests are baked into the binary: changing `ios.infoPlist`, config-plugin permission text, or `ios.privacyManifests` requires a new EAS build and store submission (not OTA). Expo's guide says Apple may not read PrivacyInfo from static-pod dependencies, so declare required-reason APIs (e.g. UserDefaults CA92.1) yourself.
- Runtime RTL switching (`I18nManager.forceRTL`) only applies after an app restart and does nothing on web; on web set the `dir` attribute from `getLocales()[0].textDirection` (null on Firefox). Test both directions with the `forcesRTL` plugin option in separate dev builds.
- React Native docs give no minimum touch-target size; the 44×44 pt / 48×48 dp figures are Apple HIG / Material guidance (not verified from RN docs). Enforce with `minHeight/minWidth: 44` and `hitSlop`.
- `allowFontScaling` is on by default — layouts must survive 2×+ font scale; cap only where truncation would break meaning using `maxFontSizeMultiplier`. There is no Expo high-contrast helper; combine `useColorScheme()` with `AccessibilityInfo.isHighTextContrastEnabled()` (Android) / `isDarkerSystemColorsEnabled()` (iOS).
- @testing-library/react-native 14 needs the new `test-renderer` package (peer `^1.0.0`); the Expo unit-testing guide's install command does not include it, so add `npm i -D test-renderer` if render() fails. Remove any `react-test-renderer` (deprecated, no React 19 support).
- Typed routes generate `expo-env.d.ts` only after `npx expo start` (or `npx expo customize tsconfig.json`) runs; CI type-check (`npx tsc --noEmit`) will fail on typed `href`s until that file exists — run `npx expo customize tsconfig.json` or start the CLI once in CI before `tsc`.

## Key facts

| Fact | Source | Confidence |
|---|---|---|
| Expo SDK 57 is the current stable release; expo@57.0.24 is npm `latest` (published 2026-09-18). SDK 58 is in beta since Sept 15, 2026 (expo@next = 58.0.0-preview.6) with React Native 0.88 RC. | https://expo.dev/changelog/sdk-58-beta | verified |
| SDK 57 was released June 30, 2026 and updates React Native to 0.86.x (bundledNativeModules pins react-native 0.86.3, react 19.2.3). Upgrade command: npx expo install expo@^57.0.0 --fix. | https://expo.dev/changelog/sdk-57 | verified |
| docs.expo.dev/versions/latest lists SDK 57.0.0 with React Native 0.86, React 19.2.3, minimum Node 22.13.x. | https://docs.expo.dev/versions/latest/ | verified |
| "SDK 55 and later run entirely on the New Architecture. The New Architecture is always enabled and cannot be disabled." (legacy only on SDK 54 or earlier). | https://docs.expo.dev/guides/new-architecture/ | verified |
| `npx create-expo-app@latest` uses the `default` template, which "Includes recommended tools such as Expo CLI, Expo Router library and TypeScript configuration enabled." Other templates: blank, blank-typescript (no router), tabs (Router + TS), bare-minimum. Flags: --template, --example, --yes, --no-install, --no-agents-md. | https://docs.expo.dev/more/create-expo/ | verified |
| SDK 57 default template (expo-template-default 57.0.26) uses src/app with NativeTabs from 'expo-router/unstable-native-tabs', app.json web.output 'static', experiments.typedRoutes true and reactCompiler true, TypeScript ~6.0.3, react-native-web ~0.21.0. | https://github.com/expo/expo/tree/sdk-57/templates/expo-template-default | verified |
| SDK 58 beta: try with `npx create-expo-app@latest --template default@next` or `npx expo install expo@next --fix`; breaking changes include expo-file-system File.write() becoming async (use writeSync), expo-sqlite libSQL removal, expo-localization iOS RTL now following I18nManager; native tabs, middleware, data loaders and SSR are stable. | https://expo.dev/changelog/sdk-58-beta | verified |
| expo-camera supports Android, iOS, Web, Expo Go; API is CameraView + useCameraPermissions + takePictureAsync({quality, base64, exif, skipProcessing}); on web "Image URIs are always returned as base64 strings"; config plugin keys cameraPermission and microphonePermission. | https://docs.expo.dev/versions/latest/sdk/camera/ | verified |
| expo-image-picker supports Android, iOS, Web, Expo Go; mediaTypes is now an array (['images']); on web launchers must be called inside user activation, cancel is not reported, permission requests "do nothing on web", and the asset includes a web-only `file: File`. | https://docs.expo.dev/versions/latest/sdk/imagepicker/ | verified |
| expo-image-manipulator supports Android, iOS, tvOS, Web, Expo Go; use ImageManipulator.manipulate(uri).resize().renderAsync() then saveAsync({compress, format: SaveFormat.JPEG, base64}); manipulateAsync is deprecated. | https://docs.expo.dev/versions/latest/sdk/imagemanipulator/ | verified |
| expo-speech supports Android, iOS, Web, Expo Go; Speech.speak(text, {language (BCP 47), voice (identifier), pitch, rate, volume, onDone...}); getAvailableVoicesAsync returns Voice{identifier,name,language,quality}; pause/resume are iOS+web only; iOS silent mode mutes it; onError not on web. | https://docs.expo.dev/versions/latest/sdk/speech/ | verified |
| expo-print: printToFileAsync({html,width,height,base64,margins}) returns {uri, numberOfPages, base64?}; "On Web this method opens the print dialog" (no PDF file); printAsync "On web this prints the HTML from the page." | https://docs.expo.dev/versions/latest/sdk/print/ | verified |
| expo-sharing on web relies on the Web Share API with "very limited browser support", requires HTTPS, and "Sharing local files by URI works on Android and iOS, but not on web." Gate with Sharing.isAvailableAsync(). | https://docs.expo.dev/versions/latest/sdk/sharing/ | verified |
| expo-secure-store platforms are Android, iOS, tvOS, Expo Go — web is not supported; "some iOS releases refused values above roughly 2048 bytes"; requireAuthentication unsupported in Expo Go; iOS keychain data persists across reinstall. | https://docs.expo.dev/versions/latest/sdk/securestore/ | verified |
| expo-sqlite supports Android, iOS, macOS, tvOS, Web ("Web support is in alpha and may be unstable"), Expo Go; web needs metro assetExts 'wasm' plus Cross-Origin-Embedder-Policy: credentialless and Cross-Origin-Opener-Policy: same-origin headers; expo-sqlite/kv-store is an AsyncStorage drop-in. | https://docs.expo.dev/versions/latest/sdk/sqlite/ | verified |
| @react-native-async-storage/async-storage is installed via `npx expo install @react-native-async-storage/async-storage` and supports Android, iOS, macOS, tvOS, Web, Expo Go; Expo SDK 57 pins version 2.2.0 while npm latest is 3.1.1. | https://docs.expo.dev/versions/latest/sdk/async-storage/ | verified |
| expo-file-system (new File/Directory/Paths API) lists platforms Android, iOS, tvOS, Expo Go — no web; legacy API available at 'expo-file-system/legacy'; File.downloadFileAsync(url, directory) downloads files. | https://docs.expo.dev/versions/latest/sdk/filesystem/ | verified |
| expo-localization supports Android, iOS, tvOS, Web, Expo Go; getLocales()[0] gives languageTag, languageCode, regionCode, textDirection; currencyCode and measurementSystem are null on web. | https://docs.expo.dev/versions/latest/sdk/localization/ | verified |
| "RTL support is enabled by default. Layout direction follows React Native's I18nManager." Config plugin options supportsRTL (false to opt out), forcesRTL (true to force), supportedLocales; on web set `<View dir={getLocales()[0].textDirection \|\| 'ltr'}>`; textDirection unavailable on Firefox/older browsers; runtime I18nManager.forceRTL + Updates.reloadAsync is native-only. | https://docs.expo.dev/guides/localization/ | verified |
| I18nManager.allowRTL()/forceRTL() changes "take effect on the next application start, not immediately" and persist; forceRTL is meant for development/testing. | https://reactnative.dev/docs/i18nmanager | verified |
| expo-haptics supports Android, iOS, Web (browser vibration API; may be ignored in some contexts); impactAsync/notificationAsync/selectionAsync/performAndroidHapticsAsync; VIBRATE permission auto-added. | https://docs.expo.dev/versions/latest/sdk/haptics/ | verified |
| expo-image supports Android, iOS, tvOS, Web, Expo Go with contentFit, placeholder (blurhash/thumbhash), transition, cachePolicy, recyclingKey, alt; web uses <img> with responsivePolicy/srcset and loading prop. | https://docs.expo.dev/versions/latest/sdk/image/ | verified |
| expo-document-picker getDocumentAsync({type:'application/pdf', multiple, copyToCacheDirectory, base64(web)}) returns {canceled, assets[{uri,name,size,mimeType, file(web)}]}; web requires user activation and cancel events are unreliable. | https://docs.expo.dev/versions/latest/sdk/document-picker/ | verified |
| expo-clipboard on web uses the AsyncClipboard API which "might behave differently between browsers or not be fully supported"; getStringAsync prompts for clipboard-read permission; a WebKit issue "makes this API unusable in asynchronous code". | https://docs.expo.dev/versions/latest/sdk/clipboard/ | verified |
| expo-speech-recognition (jamsch, community) latest 57.1.0 with SDK-aligned dist-tags; requires a development build (not Expo Go); iOS 17+, Android 12+; web via Web Speech API on Chrome, Safari 16+, Edge (not Firefox/Brave); config plugin microphonePermission/speechRecognitionPermission/androidSpeechServicePackages. | https://github.com/jamsch/expo-speech-recognition | verified |
| expo-router@57.0.22 is current (SDK-aligned versioning); route notation: _layout.tsx, index.tsx, [param].tsx, (group), +not-found.tsx, +html.tsx, +native-intent.tsx, +middleware.ts; src/app takes precedence over app/. | https://docs.expo.dev/router/basics/notation/ | verified |
| Native tabs import path is 'expo-router/unstable-native-tabs' on SDK 54–57 and stable 'expo-router/native-tabs' on SDK 58+; on web native tabs fall back to a basic implementation and docs recommend _layout.web.tsx with expo-router/ui. | https://docs.expo.dev/router/advanced/native-tabs/ | verified |
| Typed routes are enabled via experiments.typedRoutes: true in app.json; Expo CLI generates a git-ignored expo-env.d.ts; Link href and router.push become type-checked. | https://docs.expo.dev/router/reference/typed-routes/ | verified |
| web.output is one of single (SPA, "Defaults to `single`"), static (HTML per route), server (static HTML + API routes); export with `npx expo export --platform web` to dist/. | https://docs.expo.dev/versions/latest/config/app/ | verified |
| Static export: set web.output 'static', run `npx expo export --platform web`, output is dist/ (public/ copied in), test with `npx serve dist`; deployable to Netlify, Vercel, Cloudflare Pages, GitHub Pages, etc. | https://docs.expo.dev/router/reference/static-rendering/ | verified |
| Hosting recipes: EAS Hosting via `eas deploy`; Vercel via vercel.json {buildCommand: 'expo export -p web', outputDirectory: 'dist', rewrites to '/'}; Netlify via public/_redirects `/* /index.html 200` and `netlify deploy --dir dist`; GitHub Pages via experiments.baseUrl + gh-pages. | https://docs.expo.dev/guides/publishing-websites/ | verified |
| EAS Hosting: `npx expo export --platform web` then `eas deploy` (first run picks a subdomain, URLs like https://my-app.expo.app); runs on Cloudflare Workers with partial Node.js support; API routes supported with server output; custom domains are paid-plan only. | https://docs.expo.dev/eas/hosting/get-started/ | verified |
| EAS Free plan: $0, "15 Android and 15 iOS builds" per month on a low-priority queue, 45-minute build timeout, 1 concurrency, no large workers; EAS Update 1K MAU; EAS Submit included; EAS Hosting 100,000 requests, 1,000,000 CPU-ms, 1 GB storage, 5 aliases. Starter $19/mo, Production $199/mo; usage builds $1 Android / $2 iOS medium. | https://expo.dev/pricing | verified |
| EAS Build compiles iOS on "macOS runners hosted in Expo's macOS cloud" (no local Mac needed); setup: npm install --global eas-cli, eas login, eas build:configure, eas build --platform ios\|android\|all; Apple Developer Program $99/yr and Google Play $25 one-time are required for store distribution. | https://docs.expo.dev/build/setup/ | verified |
| EAS Submit: `eas submit --platform ios` (needs paid Apple Developer account, ascAppId, Apple ID or ASC API key; "you don't need a Mac to ship iOS builds") and `eas submit --platform android` (.aab, Google service account JSON, first release to internal track); `eas build --auto-submit` chains them. | https://docs.expo.dev/submit/ios/ | verified |
| eas.json: cli.appVersionSource 'remote' (recommended since EAS CLI 12) with build.production.autoIncrement true lets EAS manage ios.buildNumber / android.versionCode; app.json `version` is the user-facing store version. | https://docs.expo.dev/build-reference/app-versions/ | verified |
| Store identifiers: ios.bundleIdentifier ("needs to be unique on the App Store") and android.package (reverse-DNS, "unique on the Play Store"); ios.infoPlist adds Info.plist keys such as NSCameraUsageDescription; ios.privacyManifests writes PrivacyInfo.xcprivacy; android.permissions / android.blockedPermissions control the manifest. | https://docs.expo.dev/versions/latest/config/app/ | verified |
| Permission strings go in ios.infoPlist (or library config plugins); "Changes to the Info.plist cannot be updated over-the-air, they will only be deployed when you submit a new native binary". | https://docs.expo.dev/guides/permissions/ | verified |
| Apple privacy manifests: "Apple does not correctly parse all the PrivacyInfo files included by static CocoaPods dependencies (such as Expo SDK packages…)", so declare required-reason APIs in app.json ios.privacyManifests.NSPrivacyAccessedAPITypes (e.g. NSPrivacyAccessedAPICategoryUserDefaults, reason CA92.1). | https://docs.expo.dev/guides/apple-privacy/ | verified |
| Expo Go "cannot use third-party libraries that require custom native code" and "is limited and not useful for building production-grade projects"; development builds (expo-dev-client; `eas build --profile development` or `npx expo run:ios\|android`) are strongly recommended. | https://docs.expo.dev/faq/ | verified |
| As of May 2026 the App Store version of Expo Go supports SDK 54 while newer SDK versions await Apple approval; `eas go` builds your own Expo Go to TestFlight (requires Apple Developer membership); SDK 57/58 Expo Go is otherwise only available via Expo CLI for Android devices and iOS simulators. | https://expo.dev/changelog/expo-go-and-app-store-may-2026 | verified |
| React Native accessibility props: accessible, accessibilityLabel, accessibilityHint, accessibilityRole, accessibilityState, accessibilityValue, accessibilityLiveRegion, importantForAccessibility, accessibilityActions/onAccessibilityAction, plus aria-* aliases and a `role` prop that takes priority over accessibilityRole. | https://reactnative.dev/docs/accessibility | verified |
| AccessibilityInfo exposes isScreenReaderEnabled, isReduceMotionEnabled, isBoldTextEnabled (iOS), isHighTextContrastEnabled (Android), isDarkerSystemColorsEnabled (iOS), isInvertColorsEnabled, isGrayscaleEnabled, isReduceTransparencyEnabled, announceForAccessibility, announceForAccessibilityWithOptions, sendAccessibilityEvent (setAccessibilityFocus deprecated). | https://reactnative.dev/docs/accessibilityinfo | verified |
| Text: allowFontScaling defaults to true ("respect Text Size accessibility settings"); maxFontSizeMultiplier caps scaling (0 = no max, >=1 = cap); iOS dynamicTypeRamp (caption2…largeTitle, default body); adjustsFontSizeToFit + minimumFontScale. | https://reactnative.dev/docs/text | verified |
| PixelRatio.getFontScale() returns the font-size scaling factor from Android Settings > Display > Font size or iOS Text Size / Larger Text. | https://reactnative.dev/docs/pixelratio | verified |
| React Native docs state no minimum touch-target size; Pressable offers hitSlop ("additional distance outside of element in which a press can be detected") and pressRetentionOffset. The 44pt/48dp minimums are Apple HIG / Material guidance, not RN docs. | https://reactnative.dev/docs/pressable | likely |
| Dark mode: app.json userInterfaceStyle 'automatic' \| 'light' \| 'dark'; use useColorScheme() or Appearance.getColorScheme()/addChangeListener from react-native; Android development builds need expo-system-ui installed or userInterfaceStyle is ignored. | https://docs.expo.dev/develop/user-interface/color-themes/ | verified |
| Unit testing: `npx expo install jest-expo jest @types/jest --dev`, package.json "jest": {"preset": "jest-expo"}, script "test": "jest --watchAll", add "jest" to tsconfig types; `npx expo install @testing-library/react-native --dev`; RNTL replaces deprecated react-test-renderer (no React 19 support). | https://docs.expo.dev/develop/unit-testing/ | verified |
| jest-expo presets: jest-expo (default), jest-expo/ios, jest-expo/android, jest-expo/web, jest-expo/node, jest-expo/universal; platform tests via -test.ios.tsx etc.; snapshots saved per platform (.snap.ios, .snap.web). | https://github.com/expo/expo/tree/sdk-57/packages/jest-expo | verified |
| @testing-library/react-native 14.0.1 peer deps: jest >=29 (optional), react >=19, react-native >=0.78, test-renderer ^1.0.0; matchers are built in once you import from the library. | https://registry.npmjs.org/@testing-library/react-native/latest | verified |
| Type checking: docs say run `tsc` from the project root; expo/tsconfig.base sets noEmit: true (plus jsx react-jsx, moduleResolution bundler, customConditions ['react-native'], skipLibCheck), so `npx tsc` and `npx tsc --noEmit` behave the same; generate tsconfig with `npx expo customize tsconfig.json`; enable strict; path alias @/* -> src/*. | https://docs.expo.dev/guides/typescript/ | verified |
