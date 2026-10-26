# Third-party notices and credits

ProxyHealth AI is built on the open-source software, fonts and services below. This file documents them, as the Congressional App Challenge rules require ("participants may use open-source libraries, frameworks, and external tools, [but] they must clearly document any such usage"). Versions are the ones locked in this repository on 2026-10-22. Each package's full license text ships with the package (`apps/mobile/node_modules/<name>/LICENSE*`, `apps/api/.venv/lib/python3.13/site-packages/<name>-*.dist-info/`).

## Development tools

- Expo CLI 57.0.26 / Expo SDK 57 (MIT) - dev server, web export, prebuild
- EAS CLI (run via npx eas-cli@latest, not installed) - cloud builds and submission
- Node.js 24.21.0 LTS + npm 11.19.0 (MIT / Artistic-2.0)
- Metro 0.84.5, Babel 7.29.7, Hermes compiler (MIT; ship inside expo/react-native)
- TypeScript 6.0.3 (Apache-2.0), ESLint 9.39.5 (MIT), Jest 29.7.0 (MIT), openapi-typescript 7.13.0 (MIT)
- Python 3.13.7 (python.org; PSF-2.0) with venv tools pytest 9.1.1, ruff 0.16.8, mypy 2.3.1, coverage 7.16.1
- git 2.50.1 (Apple Git-155; GPL-2.0, a tool only, does not affect the app's license)
- GNU Make + bash/zsh scripts (Makefile, scripts/ci.sh 15-step CI, smoke.sh, dev.sh)
- Docker (apps/api/Dockerfile, base python:3.13-slim; Docker not installed on this Mac)
- Google Chrome / browser preview for testing the web build
- apps/api/scripts/gen_packs.py - checks (`--check`) and assembles the bundled UI language packs; it can also generate packs through the Google Gemini API (MODEL_FAST)

## External services the app can call at runtime

| Name | Role |
|---|---|
| Apple App Store / Google Play | Planned distribution channels (docs/STORE_LISTING.md) |
| Built-in mock provider | Default (AI_PROVIDER=mock): makes no external calls and needs zero keys. Serves the 18 synthetic samples for judges and demos. |
| Device OS services (camera, photo library, file picker, text-to-speech, local notifications, printing, share sheet) | On-device only, through Expo modules; no third-party push or analytics service |
| Expo Application Services (EAS Build/Submit, EAS Hosting at proxyhealth.expo.app) | Native store builds and web/privacy-policy hosting. Cloudflare Pages or Netlify are alternative static hosts. |
| Google Cloud Run (+ Secret Manager, Cloud Logging) | Planned API host (docs/DEPLOYMENT.md), plus a second mock-only demo service for judges. Fly.io and Render are documented alternatives. |
| Google Gemini API (google-genai SDK; default models gemini-3.8-flash for MODEL_PRO and gemini-3.5-flash-lite for MODEL_FAST) | Reads and explains papers, translation and chat when AI_PROVIDER=gemini. Subject to the Google APIs Terms and the Gemini API Additional Terms: users must be 18+, and free-tier data may be used for training, so real papers go only to the paid tier. The gen_packs.py script can also generate UI language packs through it. |
| OpenAI-compatible /chat/completions endpoint (default Ollama, MIT, at 127.0.0.1:11434 running Qwen3.5 4B open weights, Apache-2.0) | Optional provider for test builds only (AI_PROVIDER=openai_compat; ENV=production refuses it). Neither Ollama nor the model is installed on this machine. |
| Public resource websites and phone lines (68 domains, e.g. healthcare.gov, uscis.gov, irs.gov, 988lifeline.org, lawhelp.org) | Only opened when the user taps them (expo-web-browser or the phone dialer); the app never fetches them at runtime. The dev script apps/api/scripts/check_links.py fetches them to check the links. |

## Mobile / web app — runtime packages (npm)

| Name | Version | License | Purpose |
|---|---|---|---|
| @expo/ui | 57.0.19 | MIT | Left over from the Expo template; listed in package.json but never imported |
| @react-native-async-storage/async-storage | 2.2.0 | MIT | Key-value storage for settings on the device |
| expo | 57.0.24 | MIT | Expo SDK 57 runtime and CLI (bundles @expo/cli 57.0.26, Metro 0.84.5, Babel 7.29.7, Hermes; all MIT); one codebase for iOS, Android and web |
| expo-camera | 57.0.5 | MIT | Takes photos of paper documents |
| expo-clipboard | 57.0.2 | MIT | Copies phone numbers and text |
| expo-constants | 57.0.19 | MIT | Reads app config (API URL, app version) |
| expo-crypto | 57.0.3 | MIT | Hashing and random ids on the device |
| expo-dev-client | 57.0.19 | MIT | Development builds only (EAS 'development' profile); not used in the web build |
| expo-device | 57.0.2 | MIT | Left over from the Expo template; never imported |
| expo-document-picker | 57.0.2 | MIT | Picks a PDF or image file from the device |
| expo-file-system | 57.0.7 | MIT | Local storage of saved papers and generated files (native only; web uses Blob URLs) |
| expo-font | 57.0.4 | MIT | Loads the bundled Noto fonts |
| expo-glass-effect | 57.0.3 | MIT | Left over from the Expo template; never imported |
| expo-haptics | 57.0.3 | MIT | Haptic feedback on actions |
| expo-image | 57.0.5 | MIT | Shows page images and sample papers (7 files) |
| expo-image-manipulator | 57.0.19 | MIT | Crops, resizes and masks page images on the device before upload |
| expo-image-picker | 57.0.19 | MIT | Picks a photo or screenshot from the device library |
| expo-linking | 57.0.10 | MIT | Deep links; required by expo-router (not imported directly) |
| expo-localization | 57.0.2 | MIT | Detects device language and right-to-left layout |
| expo-network | 57.0.2 | MIT | Offline detection |
| expo-notifications | 57.0.20 | MIT | Local deadline reminders scheduled on the device (no push service) |
| expo-print | 57.0.2 | MIT | Prints the one-page quick sheet |
| expo-router | 57.0.22 | MIT | File-based navigation in src/app (imported in 52 files) |
| expo-secure-store | 57.0.4 | MIT | Encrypted on-device storage for secrets (web shim) |
| expo-sharing | 57.0.21 | MIT | Shares the quick-sheet PDF to other apps |
| expo-speech | 57.0.3 | MIT | Reads explanations aloud with the device's text-to-speech |
| expo-splash-screen | 57.0.9 | MIT | Splash screen while the app loads |
| expo-sqlite | 57.0.3 | MIT | On-device database for saved papers/history |
| expo-status-bar | 57.0.1 | MIT | Status bar styling |
| expo-symbols | 57.0.3 | MIT | Left over from the Expo template; never imported (the app uses its own SVG icons) |
| expo-system-ui | 57.0.4 | MIT | Left over from the Expo template; never imported |
| expo-web-browser | 57.0.3 | MIT | Opens resource websites in an in-app browser |
| react | 19.2.3 | MIT | UI component library (imported in 89 source files) |
| react-dom | 19.2.3 | MIT | Web renderer for the web build (not imported directly) |
| react-native | 0.86.3 | MIT | Native UI framework (imported in 121 source files) |
| react-native-gesture-handler | 2.32.0 | MIT | Touch/gesture system required by expo-router navigation (peer dependency, not imported directly) |
| react-native-reanimated | 4.5.1 | MIT | Animation engine required by the navigation stack (peer dependency, not imported directly) |
| react-native-safe-area-context | 5.7.0 | MIT | Keeps screens clear of the notch and system bars (9 files) |
| react-native-screens | 4.26.2 | MIT | Native screen containers used by expo-router (peer dependency, not imported directly) |
| react-native-svg | 15.15.4 | MIT | Draws the app's own vector icons (design/components/Icon.tsx) |
| react-native-web | 0.21.2 | MIT | Runs React Native components in the browser for the web build (not imported directly) |
| react-native-worklets | 0.10.1 | MIT | Threading runtime required by react-native-reanimated (peer dependency, not imported directly) |
| zustand | 5.0.15 | MIT | App state stores (10 files) |

## Mobile / web app — development packages (npm)

| Name | Version | License | Purpose |
|---|---|---|---|
| @react-native/jest-preset | 0.86.3 | MIT | React Native Jest preset (peer of jest-expo) |
| @testing-library/react-native | 14.0.1 | MIT | Component tests (44 test files) |
| @types/jest | 29.5.14 | MIT | TypeScript types for Jest |
| @types/react | 19.2.18 | MIT | TypeScript types for React |
| eslint | 9.39.5 | MIT | Linting (npx expo lint) |
| eslint-config-expo | 57.0.2 | MIT | Expo lint rules |
| jest | 29.7.0 | MIT | Mobile test runner (64 suites, 566 tests) |
| jest-expo | 57.0.5 | MIT | Jest preset for Expo/React Native |
| openapi-typescript | 7.13.0 | MIT | Generates src/api/schema.d.ts from apps/api/openapi.json |
| test-renderer | 1.3.0 | MIT | Renderer used by @testing-library/react-native v14 |
| typescript | 6.0.3 | Apache-2.0 | Type checking (npx tsc --noEmit) |

## API server — Python packages

| Name | Version | License | Purpose |
|---|---|---|---|
| arabic-reshaper | 3.0.1 | MIT | Arabic-script letter shaping for PDFs and fixture images |
| certifi | 2026.7.22 | MPL-2.0 | Transitive (via httpx): Mozilla CA certificate bundle for HTTPS |
| CPython (Docker base python:3.13-slim) | 3.13.7 locally | PSF-2.0 (Debian slim base image: mixed open-source licenses) | Runs the API server |
| fastapi | 0.141.1 | MIT | HTTP API framework |
| google-genai | 2.25.0 | Apache-2.0 | Google Gemini API client (AI_PROVIDER=gemini); pulls google-auth 2.58.0 (Apache-2.0), requests 2.34.2 (Apache-2.0), tenacity 9.1.4 (Apache-2.0) |
| httpx | 0.28.1 | BSD-3-Clause | HTTP client for the openai_compat provider, link checker and tests |
| limits | 5.8.0 | MIT | Rate limiting engine (imported directly in ratelimit.py) |
| mypy | 2.3.1 | MIT | Dev: strict type checking |
| pillow | 12.3.0 | MIT-CMU (HPND) | Image decoding/normalising, sample-fixture rendering, app-icon drawing (make_artwork.py) |
| pydantic | 2.13.5 | MIT | Request/response models and validation of model output |
| pydantic-settings | 2.15.0 | MIT | Settings from environment / .env (uses python-dotenv 1.2.3, BSD-3-Clause) |
| pypdfium2 | 5.13.0 | BSD-3-Clause / Apache-2.0 (bundled PDFium binary and its permissive dependencies) | Renders uploaded PDF pages to images |
| pytest | 9.1.1 | MIT | Dev: API tests (3,403 passing; 28 live-only tests skip without keys) |
| pytest-asyncio | 1.4.0 | Apache-2.0 | Dev: async tests |
| pytest-cov | 7.1.0 | MIT | Dev: coverage (coverage 7.16.1, Apache-2.0) |
| python-bidi | 0.6.11 | LGPL-3.0-or-later | Right-to-left text ordering for PDFs and fixture images (server-side only) |
| python-multipart | 0.0.32 | Apache-2.0 | Multipart image uploads in FastAPI (not imported directly) |
| PyYAML | 6.0.3 | MIT | Loads the resource DB, rules, safety lists and fixture templates |
| reportlab | 5.0.1 | BSD-3-Clause (ReportLab Inc.) | Builds the quick-sheet PDF |
| ruff | 0.16.8 | MIT | Dev: Python lint |
| slowapi | 0.1.10 | MIT | Installed and pinned (pulls in limits) but not imported; the code uses limits directly |
| starlette | 1.7.0 | BSD-3-Clause | ASGI toolkit under FastAPI; middleware imported directly |
| types-PyYAML | 6.0.12.20260906 | Apache-2.0 | Dev: type stubs for PyYAML |
| uvicorn | 0.53.0 | BSD-3-Clause | ASGI server (Dockerfile CMD, make dev); with uvloop 0.22.1 (MIT/Apache-2.0), httptools 0.8.0 (MIT), watchfiles 1.3.0 (MIT), websockets 16.1.1 (BSD-3-Clause) |

## Fonts, data and other assets

| Name | License | Where |
|---|---|---|
| 18 sample papers/screenshots (e.g. hospital bill, IRS CP notice, USCIS I-797C, jury summons, scam letter, W-2, Spanish lease) | Made by the project: synthetic, fictional data and 555-01xx phone numbers, diagonal SAMPLE watermark and 'SAMPLE - synthetic document' footer; rendered by apps/api/scripts/make_fixtures.py from each sample's template.yaml, which also holds the recorded outputs (out.<lang>.json) | apps/api/data/fixtures/<id>/ (5 synced to apps/mobile/assets/fixtures/) |
| App icon, Android adaptive icons, splash, favicon, notification icon, iOS icon layer | Original artwork drawn in code by scripts/make_artwork.py (Pillow) in the project's brand colours | apps/mobile/assets/images/, apps/mobile/assets/expo.icon/ |
| CJK PDF fonts (STSong-Light, HeiseiMin-W3, HYSMyeongJo-Medium) | Not shipped: reportlab only names these standard Adobe CID fonts and the PDF viewer supplies them | apps/api/proxyhealth_api/quicksheet/fonts.py |
| Expo app template scaffold code | MIT, Copyright 2015-present 650 Industries, Inc. (Expo) | apps/mobile/LICENSE (covers only the template code) |
| Noto fonts: 9 families (Noto Sans, Sans Bengali, Devanagari, Ethiopic, Gurmukhi, Hanifi Rohingya, Myanmar, Naskh Arabic, Nastaliq Urdu), Regular and Bold, 18 TTFs | SIL Open Font License 1.1, Copyright 2018 The Noto Project Authors (OFL.txt shipped alongside) | apps/api/data/fonts/ and apps/mobile/assets/fonts/ (identical OFL.txt in both) |
| Resource database: 101 entries in 8 YAML files (6 national, 1 Northern Virginia regional, _meta) linking 68 public-organisation domains (federal and state agencies, courts, nonprofits, hotlines) | Facts only (names, phone numbers, public URLs, hours), each with verified_on and source; descriptions and checklists written by the project; no copied page content | apps/api/data/resources/ and apps/mobile/assets/resources/national_fallbacks.json |
| Safety and rule data (emergency, scam, prompt-injection and phrasing lists; deadlines, clerk needs, fixed notices, prepare checklists) | Written by the project | apps/api/data/safety/, apps/api/data/rules/ |
| Specification and research docs (14 docs/*.md + 8 docs/research/*.md) | Part of the project | docs/ |
| UI icons (about 35 glyphs) | Original SVG paths; the 'settings' gear is adapted from Feather Icons (MIT License, Copyright (c) 2013-2017 Cole Bemis) | apps/mobile/src/design/components/Icon.tsx |
| UI language packs (en, plus es, ar, prs, ps) | Written by the project; non-English packs are flagged machine_translated: true, reviewed_by: null (machine translation, no human review yet; the app labels them "Translated by a computer") | apps/api/data/langpacks/, apps/mobile/src/i18n/packs/, apps/mobile/locales/ |

## Notes on specific licenses

- Project license: the repository root has no LICENSE file yet (the README says 'License: not chosen yet'). Until the owner adds one, the project's own code is all rights reserved: it can be read on GitHub but is not licensed for reuse. Every open-source component it uses is documented in this file, as the Congressional App Challenge rules require.
- apps/mobile/LICENSE is the Expo template's MIT notice (Copyright 650 Industries, Inc.), not the project's license. It sits where a reader would expect the app's own license, so a judge could read it as Expo holding rights in the app. Keep it as a third-party notice (rename it or move it into the credits file) and state the project's own license separately.
- python-bidi 0.6.11 is LGPL-3.0-or-later (weak copyleft; the wheel ships COPYING [GPLv3] + COPYING.LESSER). It is used unmodified at runtime only on the server (quick-sheet PDFs and fixture rendering) and is never in the mobile/web bundle. Hosting it as a service creates no obligations. If the Docker image is ever distributed, ship the LGPL text and keep the library replaceable (a normal Python import already allows this). Not a blocker, but list it.
- MPL-2.0 (file-level copyleft), all used unmodified: certifi (Python, via httpx, part of the runtime image), pathspec (Python dev only), lightningcss 1.33.0 + lightningcss-darwin-arm64 (npm, via @expo/metro-config, build-time only). Only a notice is needed.
- node-forge 1.4.0 is dual-licensed '(BSD-3-Clause OR GPL-2.0)'. It comes in through @expo/cli (dev-server HTTPS / code signing), is build tooling only and never in the app bundle. Use it under BSD-3-Clause; no GPL obligation.
- The reportlab 5.0.1 wheel ships the GPL-licensed DarkGarden font and the Bitstream Vera fonts. The project uses neither (quick sheet uses Noto TTFs, CID fonts or the built-in Helvetica), but they sit in the Docker image as part of reportlab's distribution. Informational only.
- No unknown or undeclared licenses: all 1049 packages in apps/mobile/node_modules declare one (912 MIT, 41 ISC, 29 Apache-2.0, 24 BSD-3, 21 BSD-2, plus small counts of BlueOak, 0BSD, CC0, Unlicense, Python-2.0, CC-BY-4.0, MPL-2.0 and the node-forge dual license), and so do all 62 venv packages. No GPL or AGPL is in shipped code.
- Feather Icons (https://feathericons.com), MIT License, Copyright (c) 2013-2017 Cole Bemis: the 'settings' gear glyph in apps/mobile/src/design/components/Icon.tsx is adapted from Feather's 'settings' icon. Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction, subject to including the copyright notice and this permission notice in all copies or substantial portions of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
- Third-party name in a sample: fixture inova_final_notice prints 'Inova Health System' (a real Northern Virginia hospital system) on a synthetic 'FINAL NOTICE' bill. It has fictional amounts and 555 numbers and is watermarked SAMPLE. CAC bars violating third parties' IP/common-law rights, so consider a fictional hospital name or a clear 'not affiliated' note. All other samples use fictional organisations or generic government formats.
- Unused template dependencies: @expo/ui, expo-glass-effect, expo-symbols, expo-device and expo-system-ui are in package.json but never imported. All are MIT, so there is no license issue; remove them or list them as unused. slowapi is likewise pinned but not imported (the code uses limits directly).

## Expo project template

`apps/mobile` was started from the Expo `default` template (`create-expo-app`). Its MIT notice, Copyright (c) 2015-present 650 Industries, Inc. (Expo), is kept in `apps/mobile/LICENSE`. That notice covers the template, not ProxyHealth AI as a whole.
