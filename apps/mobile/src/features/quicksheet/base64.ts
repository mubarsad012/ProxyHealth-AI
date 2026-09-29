// Tiny dependency-free base64 encoder for font bytes (Hermes/JSC/web alike). Pure.

const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

export function bytesToBase64(bytes: Uint8Array): string {
  const out: string[] = [];
  let chunk = '';
  const n = bytes.length;
  for (let i = 0; i < n; i += 3) {
    const a = bytes[i];
    const b = i + 1 < n ? bytes[i + 1] : 0;
    const c = i + 2 < n ? bytes[i + 2] : 0;
    const triple = (a << 16) | (b << 8) | c;
    chunk +=
      ALPHABET[(triple >> 18) & 63] +
      ALPHABET[(triple >> 12) & 63] +
      (i + 1 < n ? ALPHABET[(triple >> 6) & 63] : '=') +
      (i + 2 < n ? ALPHABET[triple & 63] : '=');
    if (chunk.length >= 8192) {
      out.push(chunk);
      chunk = '';
    }
  }
  out.push(chunk);
  return out.join('');
}
