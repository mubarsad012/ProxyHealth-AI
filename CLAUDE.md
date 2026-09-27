# ProxyHealth AI — agent notes (repo root)

Monorepo. Two apps share one API contract:

- `apps/mobile/` — Expo SDK 57 (React Native 0.86, React 19, TypeScript 6, Expo Router in `src/app/`). ONE codebase for iOS, Android and web. Expo-specific rules live in `apps/mobile/AGENTS.md` — read it before touching that app; Expo APIs change every SDK, so verify against https://docs.expo.dev/versions/v57.0.0/ rather than memory.
- `apps/api/` — Python 3.13 FastAPI. Virtualenv already exists at `apps/api/.venv` (fastapi, uvicorn, pydantic v2, pydantic-settings, google-genai 2.x, pillow, reportlab, pyyaml, python-multipart, httpx, pypdfium2, slowapi, arabic-reshaper + python-bidi (Arabic-script shaping/bidi for Pillow fixtures and reportlab PDFs — Pillow here has NO raqm); dev: pytest, pytest-asyncio, pytest-cov, ruff, mypy, types-PyYAML). Lint/type-check Python with `apps/api/.venv/bin/ruff check apps/api` and `apps/api/.venv/bin/mypy apps/api`. Run everything through it: `apps/api/.venv/bin/python`, `apps/api/.venv/bin/pytest`, `apps/api/.venv/bin/uvicorn`.
- `docs/` — the specification set (PRODUCT_SPEC, ARCHITECTURE, API_CONTRACT, AI_PROMPTS, RESOURCE_DB, DOCUMENT_TAXONOMY, COMPLIANCE_PRIVACY, BUILD_PLAN, DECISIONS). Build from these; when code and docs disagree, fix one and say which.

## Toolchain on this Mac
- Node 24 LTS is at `~/.local/node/bin` (added to `~/.zprofile`). In non-login shells run `export PATH="$HOME/.local/node/bin:$PATH"` first. No Homebrew.
- No Xcode (Command Line Tools only): `npx expo run:ios` and the iOS simulator will NOT work here. Test with `npx expo start --web` / `npx expo export --platform web`, or Expo Go on a phone. Store builds go through EAS (`npx eas-cli@latest build`).
- Type-check mobile with `cd apps/mobile && npx tsc --noEmit`; lint with `npx expo lint`; tests with `npx jest`.
- API tests: `apps/api/.venv/bin/pytest apps/api`.

## Hard rules for agents working in parallel
1. **Never run `npm install`, `npx expo install`, or `pip install` unless you are the only agent running.** All needed packages are pre-installed; if something is truly missing, stop and report it instead of installing.
2. Only write files your work package owns (see `docs/BUILD_PLAN.md`). Shared files (API contract models, generated TS types, design tokens, i18n base pack) belong to WP0 — read them, don't edit them.
3. Never create or edit `apps/mobile/ios/` or `apps/mobile/android/` — native config goes in `app.json` / config plugins.
4. Never persist user documents/images server-side, never log document content, never let the model invent phone numbers or URLs (resources come only from the vetted YAML DB).
5. Secrets only via `.env` (git-ignored). Commit `.env.example` instead.
6. The whole app must run with ZERO API keys (`AI_PROVIDER=mock`). Every feature needs a mock-provider path.

## Machine facts (don't re-derive)
- The system `python3` (python.org 3.13) has NO CA bundle for `urllib`/`ssl` (CERTIFICATE_VERIFY_FAILED). Use `curl` for downloads in scripts, or `httpx` inside the venv (bundles certifi). Noto static TTFs (9 families × Regular/Bold, OFL) are already in `apps/api/data/fonts/` and `apps/mobile/assets/fonts/` — do not re-download.

## Mobile test/tooling facts already verified on this machine (don't re-derive)
- `npx tsc --noEmit`, `npx jest`, `npx expo lint`, and `npx expo export --platform web` all pass on the scaffold. Keep them passing.
- TypeScript 6: `@types/*` are NOT auto-included; `tsconfig.json` lists `"types": ["jest"]`. Add to that list rather than relying on auto-inclusion.
- `@testing-library/react-native` v14: `render()` is **async** (`const { getByText } = await render(<X/>)`); the `screen` helper is not implemented — use the queries returned by `render`. Peer package `test-renderer` and `@react-native/jest-preset` are installed. Jest preset is `jest-expo` (configured in package.json).
- `expo-file-system` (SDK 57) is the class-based API: `import { File, Directory, Paths } from 'expo-file-system'`; legacy functions live in `expo-file-system/legacy`. It has no web implementation — web needs a Blob/`URL.createObjectURL` path.
- Web has no `expo-notifications`, `expo-secure-store` (falls back to nothing — use a web shim), or SQLite without extra setup; every device-storage/TTS/camera module needs a `Platform.OS === 'web'` fallback. Verify each module's web column at https://docs.expo.dev/versions/v57.0.0/sdk/<module>/ before use.
- Installed runtime packages beyond the template: expo-camera, expo-image-picker, expo-image-manipulator, expo-speech, expo-print, expo-sharing, expo-secure-store, expo-sqlite, expo-file-system, expo-localization, expo-haptics, expo-document-picker, expo-notifications, expo-clipboard, expo-crypto, expo-network, expo-dev-client, @react-native-async-storage/async-storage, react-native-svg, zustand. Dev: jest, jest-expo, @testing-library/react-native, test-renderer, @types/jest, openapi-typescript, eslint, eslint-config-expo.
- `npm install` in apps/mobile needs `--legacy-peer-deps` (openapi-typescript pins TypeScript 5). Only one agent may install at a time.
