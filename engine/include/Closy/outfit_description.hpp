#pragma once

#include <glm/vec3.hpp>

#include <string>
#include <vector>

namespace closy {

/** Filled from optional `closy.debug` in export JSON; controls dev-only render styling in `avatar_export`. */
enum class OutfitDebugRenderMode {
  Normal,
  Overlay,
  Silhouette,
  ClippingHotspot,
};

enum class ClippingVisualizationMode {
  Hotspot,
  Binary,
};

/**
 * Garment fit from `closy.fit`: global applies to all clothing, then region overrides per proxy mesh.
 * Legacy flat keys in JSON are merged into these fields during parse.
 */
struct OutfitGarmentFitAdjust {
  glm::vec3 globalOffset{0.f};
  glm::vec3 globalScale{1.f, 1.f, 1.f};
  float globalInflate = 0.f;

  float shrinkwrapStrength = 0.f;
  float bodyOffsetBias = 0.f;

  float torsoOffsetZ = 0.f;
  float torsoInflate = 0.f;
  /** Multiplier on Y scale for shirt torso (spine) only; 1 = neutral. */
  float torsoScaleY = 1.f;

  glm::vec3 sleevesOffset{0.f};
  float sleevesInflate = 0.f;

  float waistOffsetZ = 0.f;
  /** 0–~0.5 tightens waist (hip) width in X/Z. */
  float waistTighten = 0.f;

  /** Shirt torso: nudges hem vertically; trouser legs: nudges hem. */
  float hemOffsetY = 0.f;

  /** Legacy `sleeveOffset` (Y in arm space). */
  float legacySleeveOffsetY = 0.f;
  /** Legacy `waistAdjust` (Y on trouser hip). */
  float legacyWaistAdjustY = 0.f;
  /** Legacy flat `torsoOffsetZ` merged with torsoOffsetZ. */
  float legacyTorsoOffsetZ = 0.f;
};

struct OutfitItemDesc {
  std::string slot;
  std::string type;
  bool hasColor = false;
  glm::vec3 color{0.f};
};

struct OutfitDescription {
  std::string pose = "relaxed";
  int width = 1024;
  int height = 1024;
  std::string camera = "three_quarter";
  std::vector<OutfitItemDesc> items;
  OutfitDebugRenderMode debugRender = OutfitDebugRenderMode::Normal;
  float clippingThreshold = 0.35f;
  ClippingVisualizationMode clippingVisualization = ClippingVisualizationMode::Hotspot;
  bool clippingShowBaseUnderlay = true;
  OutfitGarmentFitAdjust garmentFit{};
};

OutfitDescription defaultDemoOutfitDescription();

} // namespace closy
