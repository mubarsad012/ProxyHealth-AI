// Web has no capture cache: picked files and data: URLs live in memory only (files.web.ts).

export const CAPTURE_CACHE_DIRS: readonly string[] = [];

export async function purgeCaptureCache(): Promise<void> {}
