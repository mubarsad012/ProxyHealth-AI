// Type declaration for the platform-resolved capture-cache module (`cache.native.ts` deletes the
// folders native capture modules write into; `cache.web.ts` is a no-op — web keeps picked files
// and data: URLs in memory only). TypeScript resolves `./cache` to this file.

/** The `Paths.cache` sub-folders written by expo-camera, expo-image-manipulator, expo-image-picker,
 *  expo-document-picker and expo-print (verified in their SDK 57 native sources). */
export declare const CAPTURE_CACHE_DIRS: readonly string[];

/** Delete every capture cache folder (full-size photos, crops, picked PDFs, printed sheets). */
export declare function purgeCaptureCache(): Promise<void>;
