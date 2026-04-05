#include <Closy/avatar_demo_outfit.hpp>
#include <Closy/Avatar.hpp>
#include <Closy/Scene.hpp>
#include <Closy/outfit_builder.hpp>
#include <Closy/outfit_description.hpp>

namespace closy {

void attachDemoOutfit(Scene& scene, Avatar* avatar) {
  if (avatar == nullptr) return;
  buildOutfitFromDescription(scene, *avatar, defaultDemoOutfitDescription());
}

} // namespace closy
