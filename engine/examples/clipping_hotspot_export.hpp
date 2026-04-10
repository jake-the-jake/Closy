#pragma once

#include <Closy/AvatarPose.hpp>
#include <Closy/gl_procs.hpp>
#include <Closy/outfit_description.hpp>

namespace closy {

class GlRenderer;
class Scene;
class Avatar;

/**
 * Renders white-on-black body and garment passes, classifies pixels by silhouette overlap + dilation,
 * optionally composites an overlay debug pass underneath. Writes PNG at `pngPath`.
 * If `clippingStatsJsonPath` is non-null, writes heuristic band histograms (for dev suggestions).
 */
bool exportClippingHotspotPng(GlProcs& glp, GlRenderer& renderer, Scene& scene, Avatar* avatar,
                              const char* pngPath, int width, int height, AvatarPosePreset pose,
                              float yaw, float pitch, const OutfitDescription& outfitDesc,
                              const char* clippingStatsJsonPath);

} // namespace closy
