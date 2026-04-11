/**
 * Rewrites an in-memory GLB so GLTFLoader never instantiates embedded images.
 * Expo / expo-gl often cannot load `data:image/*;base64,...` URLs that GLTFLoader
 * passes into TextureLoader / ImageBitmapLoader, which causes parse failures or
 * unstable runtime behavior. Stripping texture tables + texture properties keeps
 * mesh + skeleton + buffer geometry intact.
 */

const GLB_MAGIC = 0x46546c67;
const CHUNK_JSON = 0x4e4f534a; // "JSON"
const CHUNK_BIN = 0x004e4942; // "BIN\0"

const EXT_TEXTURE_ONLY = new Set([
  "KHR_texture_basisu",
  "EXT_texture_webp",
  "KHR_texture_transform",
]);

function isGltfTextureRef(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const o = value as Record<string, unknown>;
  return typeof o.index === "number" || typeof o.source === "number";
}

/** Remove glTF 2.0 *Texture properties (objects with texture index / source). */
function stripTextureRefsFromObject(node: unknown): void {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    for (const item of node) stripTextureRefsFromObject(item);
    return;
  }
  const rec = node as Record<string, unknown>;
  for (const key of Object.keys(rec)) {
    const v = rec[key];
    if (key.endsWith("Texture") && isGltfTextureRef(v)) {
      delete rec[key];
      continue;
    }
    stripTextureRefsFromObject(v);
  }
}

function purgeTextureOnlyExtensions(gltf: Record<string, unknown>): void {
  const used = gltf.extensionsUsed;
  if (Array.isArray(used)) {
    const next = used.filter((x) => typeof x === "string" && !EXT_TEXTURE_ONLY.has(x));
    if (next.length === 0) delete gltf.extensionsUsed;
    else gltf.extensionsUsed = next;
  }
  const req = gltf.extensionsRequired;
  if (Array.isArray(req)) {
    const nextR = req.filter((x) => typeof x === "string" && !EXT_TEXTURE_ONLY.has(x));
    if (nextR.length === 0) delete gltf.extensionsRequired;
    else gltf.extensionsRequired = nextR;
  }
}

/**
 * Returns a new GLB ArrayBuffer with JSON rewritten to drop all textures/images.
 * If the buffer is not a GLB v2 or JSON parse fails, returns the original buffer.
 */
export function stripEmbeddedTexturesFromGlb(arrayBuffer: ArrayBuffer): ArrayBuffer {
  const view = new DataView(arrayBuffer);
  if (view.byteLength < 20 || view.getUint32(0, true) !== GLB_MAGIC) {
    return arrayBuffer;
  }
  const version = view.getUint32(4, true);
  if (version !== 2) return arrayBuffer;

  const totalLength = view.getUint32(8, true);
  if (totalLength > view.byteLength) return arrayBuffer;

  let offset = 12;
  let jsonStart = 0;
  let jsonLen = 0;
  let binStart = 0;
  let binLen = 0;

  while (offset + 8 <= totalLength) {
    const chunkLength = view.getUint32(offset, true);
    const chunkType = view.getUint32(offset + 4, true);
    const dataStart = offset + 8;
    if (dataStart + chunkLength > totalLength) return arrayBuffer;
    if (chunkType === CHUNK_JSON) {
      jsonStart = dataStart;
      jsonLen = chunkLength;
    } else if (chunkType === CHUNK_BIN) {
      binStart = dataStart;
      binLen = chunkLength;
    }
    offset += 8 + chunkLength;
  }

  if (jsonLen === 0) return arrayBuffer;

  const jsonBytes = new Uint8Array(arrayBuffer, jsonStart, jsonLen);
  let jsonStr = new TextDecoder("utf-8").decode(jsonBytes).replace(/\0/g, "");
  while (jsonStr.length > 0 && /\s/.test(jsonStr[jsonStr.length - 1]!)) {
    jsonStr = jsonStr.slice(0, -1);
  }

  let gltf: Record<string, unknown>;
  try {
    gltf = JSON.parse(jsonStr) as Record<string, unknown>;
  } catch {
    return arrayBuffer;
  }

  gltf.textures = [];
  gltf.images = [];
  gltf.samplers = [];
  stripTextureRefsFromObject(gltf);
  purgeTextureOnlyExtensions(gltf);

  const newJsonStr = JSON.stringify(gltf);
  const jsonBuf = new TextEncoder().encode(newJsonStr);
  const pad = (4 - (jsonBuf.byteLength % 4)) % 4;
  const jsonPadded = new Uint8Array(jsonBuf.byteLength + pad);
  jsonPadded.set(jsonBuf);
  for (let i = jsonBuf.byteLength; i < jsonPadded.length; i++) jsonPadded[i] = 0x20;

  const headerSize = 12;
  const jsonChunkTotal = 8 + jsonPadded.length;
  const binChunkTotal = binLen > 0 ? 8 + binLen : 0;
  const newTotal = headerSize + jsonChunkTotal + binChunkTotal;

  const out = new ArrayBuffer(newTotal);
  const outView = new DataView(out);
  outView.setUint32(0, GLB_MAGIC, true);
  outView.setUint32(4, 2, true);
  outView.setUint32(8, newTotal, true);

  let o = 12;
  outView.setUint32(o, jsonPadded.length, true);
  outView.setUint32(o + 4, CHUNK_JSON, true);
  new Uint8Array(out, o + 8, jsonPadded.length).set(jsonPadded);
  o += 8 + jsonPadded.length;

  if (binLen > 0) {
    outView.setUint32(o, binLen, true);
    outView.setUint32(o + 4, CHUNK_BIN, true);
    new Uint8Array(out, o + 8, binLen).set(new Uint8Array(arrayBuffer, binStart, binLen));
  }

  return out;
}
