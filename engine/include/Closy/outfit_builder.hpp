#pragma once

#include <Closy/outfit_description.hpp>

#include <glm/vec3.hpp>

namespace closy {

class Avatar;
class Scene;

inline constexpr float kDefaultTopScale = 1.03f;
inline constexpr float kDefaultBottomScale = 1.02f;

glm::vec3 defaultTintForSlot(const std::string& slot, const std::string& type);

void attachTopFromSpec(Scene& scene, Avatar* avatar, const std::string& type,
                       const glm::vec3& tintRgb, float uniformScale = kDefaultTopScale);

void attachBottomFromSpec(Scene& scene, Avatar* avatar, const std::string& type,
                          const glm::vec3& tintRgb, float uniformScale = kDefaultBottomScale);

void attachShoesFromSpec(Scene& scene, Avatar* avatar, const std::string& type,
                         const glm::vec3& tintRgb, float uniformScale = 1.f);

/** Reserved for future coats; currently no geometry. */
void attachOuterwearPlaceholder(Avatar* avatar, const std::string& type);

void buildOutfitFromDescription(Scene& scene, Avatar& avatar, const OutfitDescription& desc);

} // namespace closy
