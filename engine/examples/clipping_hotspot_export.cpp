#include "clipping_hotspot_export.hpp"

#include <Closy/Avatar.hpp>
#include <Closy/AvatarPreviewExport.hpp>
#include <Closy/GlRenderer.hpp>
#include <Closy/OffscreenCapture.hpp>
#include <Closy/Renderer.hpp>
#include <Closy/Scene.hpp>
#include <Closy/write_png.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

namespace closy {

float sampleLum(const std::uint8_t* p) {
  return (0.2126f * static_cast<float>(p[0]) + 0.7152f * static_cast<float>(p[1]) +
          0.0722f * static_cast<float>(p[2])) /
         255.f;
}

void buildBinaryMask(const std::uint8_t* rgba, int w, int h, float thr,
                     std::vector<std::uint8_t>& out) {
  out.resize(static_cast<std::size_t>(w) * static_cast<std::size_t>(h));
  const int n = w * h;
  for (int i = 0; i < n; ++i) {
    out[static_cast<std::size_t>(i)] = sampleLum(rgba + i * 4) >= thr ? 1 : 0;
  }
}

void dilateMax(const std::vector<std::uint8_t>& m, int w, int h, int radius,
               std::vector<std::uint8_t>& out) {
  out.resize(m.size());
  for (int y = 0; y < h; ++y) {
    for (int x = 0; x < w; ++x) {
      std::uint8_t v = 0;
      for (int dy = -radius; dy <= radius && !v; ++dy) {
        for (int dx = -radius; dx <= radius; ++dx) {
          const int nx = x + dx;
          const int ny = y + dy;
          if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
          if (m[static_cast<std::size_t>(ny * w + nx)]) {
            v = 1;
            break;
          }
        }
      }
      out[static_cast<std::size_t>(y * w + x)] = v;
    }
  }
}

glm::vec4 overlayPassClearColor() { return {0.05f, 0.055f, 0.07f, 1.f}; }

std::uint8_t lerpU8(std::uint8_t a, std::uint8_t b, float t) {
  t = std::clamp(t, 0.f, 1.f);
  return static_cast<std::uint8_t>(std::round(static_cast<float>(a) * (1.f - t) +
                                              static_cast<float>(b) * t));
}

void compositeClipping(const std::uint8_t* bodyRgba, const std::uint8_t* garRgba, int w, int h,
                       float thr, ClippingVisualizationMode viz, bool useBase,
                       const std::uint8_t* baseRgba, std::uint8_t* dst) {
  std::vector<std::uint8_t> bM, gM, bD, gD;
  buildBinaryMask(bodyRgba, w, h, thr, bM);
  buildBinaryMask(garRgba, w, h, thr, gM);
  dilateMax(bM, w, h, 2, bD);
  dilateMax(gM, w, h, 2, gD);

  const int n = w * h;
  for (int i = 0; i < n; ++i) {
    const std::size_t si = static_cast<std::size_t>(i);
    const bool b = bM[si] != 0;
    const bool g = gM[si] != 0;
    const bool overlap = b && g;
    const bool near = !overlap && ((b && gD[si] != 0) || (g && bD[si] != 0));

    std::uint8_t rr = 16, gg = 16, bb = 18;
    if (viz == ClippingVisualizationMode::Binary) {
      if (overlap) {
        rr = gg = bb = 255;
      } else {
        rr = gg = bb = 0;
      }
    } else {
      if (overlap) {
        rr = 235;
        gg = 52;
        bb = 48;
      } else if (near) {
        rr = 255;
        gg = 214;
        bb = 58;
      } else if (b && !g) {
        rr = 42;
        gg = 78;
        bb = 138;
      } else if (g && !b) {
        rr = 52;
        gg = 132;
        bb = 88;
      }
    }

    if (useBase && baseRgba != nullptr) {
      const std::uint8_t* bp = baseRgba + i * 4;
      const float hi = (overlap || near) ? 0.78f : 0.52f;
      rr = lerpU8(bp[0], rr, hi);
      gg = lerpU8(bp[1], gg, hi);
      bb = lerpU8(bp[2], bb, hi);
    }

    dst[i * 4 + 0] = rr;
    dst[i * 4 + 1] = gg;
    dst[i * 4 + 2] = bb;
    dst[i * 4 + 3] = 255;
  }
}

bool writeClippingStatsJson(const std::uint8_t* rgba, int w, int h, const char* path) {
  if (path == nullptr || rgba == nullptr || w <= 0 || h <= 0) return false;
  const std::int64_t total = static_cast<std::int64_t>(w) * h;
  std::int64_t redAll = 0, yelAll = 0;
  std::int64_t ru = 0, rm = 0, rl = 0, yu = 0, ym = 0, yl = 0;
  std::int64_t rL = 0, rR = 0, yL = 0, yR = 0;
  const int yMidA = h / 3;
  const int yMidB = (h * 2) / 3;
  const int xMid = w / 2;

  for (int y = 0; y < h; ++y) {
    const int band = y < yMidA ? 0 : (y < yMidB ? 1 : 2);
    for (int x = 0; x < w; ++x) {
      const std::uint8_t* p = rgba + (static_cast<std::size_t>(y * w + x) * 4u);
      const bool isRed = p[0] > 200 && p[1] < 115 && p[2] < 100;
      const bool isYel = p[0] > 230 && p[1] > 160 && p[2] < 110;
      const bool left = x < xMid;
      if (isRed) {
        redAll++;
        if (band == 0)
          ru++;
        else if (band == 1)
          rm++;
        else
          rl++;
        if (left)
          rL++;
        else
          rR++;
      }
      if (isYel) {
        yelAll++;
        if (band == 0)
          yu++;
        else if (band == 1)
          ym++;
        else
          yl++;
        if (left)
          yL++;
        else
          yR++;
      }
    }
  }

  auto frac = [total](std::int64_t c) {
    return total > 0 ? static_cast<double>(c) / static_cast<double>(total) : 0.0;
  };

  nlohmann::json j;
  j["version"] = 1;
  j["width"] = w;
  j["height"] = h;
  j["overlapFrac"] = frac(redAll);
  j["nearFrac"] = frac(yelAll);
  j["bands"] = {
      {"upper", frac(ru)},
      {"middle", frac(rm)},
      {"lower", frac(rl)},
  };
  j["yellowBands"] = {
      {"upper", frac(yu)},
      {"middle", frac(ym)},
      {"lower", frac(yl)},
  };
  j["halves"] = {
      {"left", frac(rL)},
      {"right", frac(rR)},
  };
  j["yellowHalves"] = {
      {"left", frac(yL)},
      {"right", frac(yR)},
  };

  std::ofstream f(path, std::ios::binary);
  if (!f) {
    std::fprintf(stderr, "[closy] Could not write clipping stats: %s\n", path);
    return false;
  }
  f << j.dump(2);
  return true;
}

bool exportClippingHotspotPng(GlProcs& glp, GlRenderer& renderer, Scene& scene, Avatar* avatar,
                              const char* pngPath, int width, int height, AvatarPosePreset pose,
                              float yaw, float pitch, const OutfitDescription& outfitDesc,
                              const char* clippingStatsJsonPath) {
  if (pngPath == nullptr || avatar == nullptr) return false;

  avatar->setPosePreset(pose);
  scene.update();

  const glm::vec3 focus = avatar->focusPointWorld();
  const float aspect = static_cast<float>(width) / static_cast<float>(height);
  const glm::mat4 view = avatarExportView(focus, yaw, pitch, kAvatarExportDistance);
  const glm::mat4 proj = avatarExportProjection(aspect, kAvatarExportFovDeg);

  const glm::vec4 maskClear(0.f, 0.f, 0.f, 1.f);
  std::vector<std::uint8_t> bodyRgba, garRgba, baseRgba;

  avatar->setDebugRenderMode(OutfitDebugRenderMode::Normal);
  avatar->setClippingMaskPass(Avatar::ClippingMaskPass::BodyWhite);
  if (!captureFrameToRgba(glp, renderer, width, height, maskClear,
                          [&](Renderer& r) { scene.render(r, view, proj); }, bodyRgba) ||
      bodyRgba.empty()) {
    std::fprintf(stderr, "[closy] Clipping pass (body mask) failed\n");
    avatar->setClippingMaskPass(Avatar::ClippingMaskPass::Off);
    return false;
  }

  avatar->setClippingMaskPass(Avatar::ClippingMaskPass::GarmentWhite);
  if (!captureFrameToRgba(glp, renderer, width, height, maskClear,
                          [&](Renderer& r) { scene.render(r, view, proj); }, garRgba) ||
      garRgba.empty()) {
    std::fprintf(stderr, "[closy] Clipping pass (garment mask) failed\n");
    avatar->setClippingMaskPass(Avatar::ClippingMaskPass::Off);
    return false;
  }

  avatar->setClippingMaskPass(Avatar::ClippingMaskPass::Off);

  const std::uint8_t* basePtr = nullptr;
  if (outfitDesc.clippingShowBaseUnderlay) {
    avatar->setDebugRenderMode(OutfitDebugRenderMode::Overlay);
    if (!captureFrameToRgba(glp, renderer, width, height, overlayPassClearColor(),
                            [&](Renderer& r) { scene.render(r, view, proj); }, baseRgba) ||
        baseRgba.empty()) {
      std::fprintf(stderr, "[closy] Clipping base (overlay) pass failed\n");
      avatar->setDebugRenderMode(OutfitDebugRenderMode::Normal);
      return false;
    }
    basePtr = baseRgba.data();
  }

  avatar->setDebugRenderMode(OutfitDebugRenderMode::Normal);

  const float thr = std::clamp(outfitDesc.clippingThreshold, 0.05f, 0.95f);
  std::vector<std::uint8_t> out(
      static_cast<std::size_t>(width) * static_cast<std::size_t>(height) * 4u);
  compositeClipping(bodyRgba.data(), garRgba.data(), width, height, thr,
                    outfitDesc.clippingVisualization, outfitDesc.clippingShowBaseUnderlay, basePtr,
                    out.data());

  if (!writePngRgba8(pngPath, width, height, out.data())) {
    std::fprintf(stderr, "[closy] PNG write failed: %s\n", pngPath);
    return false;
  }

  if (clippingStatsJsonPath != nullptr && clippingStatsJsonPath[0] != '\0') {
    if (writeClippingStatsJson(out.data(), width, height, clippingStatsJsonPath))
      std::printf("[closy] Clipping stats: %s\n", clippingStatsJsonPath);
  }

  std::printf("[closy] Exported (clipping hotspot): %s\n", pngPath);
  std::printf("[closy] Pose: %s\n", avatarPosePresetLabel(pose));
  std::printf("[closy] Size: %ix%i threshold=%.2f vis=%s underlay=%s\n", width, height, thr,
              outfitDesc.clippingVisualization == ClippingVisualizationMode::Binary ? "binary"
                                                                                     : "hotspot",
              outfitDesc.clippingShowBaseUnderlay ? "on" : "off");
  return true;
}

} // namespace closy
