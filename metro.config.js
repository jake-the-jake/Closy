const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");

/** @type {import('expo/metro-config').MetroConfig} */
const config = getDefaultConfig(__dirname);

/** Binary glTF; ensure Metro treats `.glb` as a static asset (Expo usually includes it — safe if duplicate). */
if (!config.resolver.assetExts.includes("glb")) {
  config.resolver.assetExts.push("glb");
}

const zustandMiddlewareCjs = path.resolve(
  __dirname,
  "node_modules/zustand/middleware.js",
);
const threeRoot = path.resolve(__dirname, "node_modules/three");

config.resolver.extraNodeModules = {
  ...(config.resolver.extraNodeModules || {}),
  three: threeRoot,
};

/**
 * Web: package exports send `zustand/middleware` to `esm/middleware.mjs`, which uses
 * `import.meta.env`. Metro emits that into the RN Web bundle; the browser then throws
 * "import.meta may only appear in a module" and React never hydrates — clicks/UI updates
 * appear broken. Force the CommonJS build (`process.env.NODE_ENV`), which matches native.
 */
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === "web" && moduleName === "zustand/middleware") {
    return {
      filePath: zustandMiddlewareCjs,
      type: "sourceFile",
    };
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
