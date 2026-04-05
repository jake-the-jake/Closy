#include <Closy/outfit_builder.hpp>
#include <Closy/Avatar.hpp>
#include <Closy/Mesh.hpp>
#include <Closy/Scene.hpp>

#include <cctype>
#include <cstdio>

namespace closy {
namespace {

bool ieq(std::string a, std::string b) {
  for (auto& c : a)
    c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  for (auto& c : b)
    c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
  return a == b;
}

} // namespace

OutfitDescription defaultDemoOutfitDescription() {
  OutfitDescription d;
  d.pose = "relaxed";
  d.width = 1024;
  d.height = 1024;
  d.camera = "three_quarter";
  OutfitItemDesc top;
  top.slot = "top";
  top.type = "jumper";
  top.hasColor = false;
  OutfitItemDesc bottom;
  bottom.slot = "bottom";
  bottom.type = "trousers";
  bottom.hasColor = false;
  d.items.push_back(top);
  d.items.push_back(bottom);
  return d;
}

glm::vec3 defaultTintForSlot(const std::string& slot, const std::string& type) {
  if (ieq(slot, "top"))
    return {0.42f, 0.52f, 0.82f};
  if (ieq(slot, "bottom"))
    return {0.34f, 0.38f, 0.48f};
  if (ieq(slot, "shoes"))
    return {0.20f, 0.17f, 0.15f};
  (void)type;
  return {0.55f, 0.55f, 0.58f};
}

void attachTopFromSpec(Scene& scene, Avatar* avatar, const std::string& type,
                       const glm::vec3& tintRgb, float uniformScale) {
  if (avatar == nullptr) return;
  const bool jumperLike = ieq(type, "jumper") || ieq(type, "shirt");
  if (!jumperLike && !ieq(type, "generic")) {
    std::fprintf(stderr, "[closy] Unknown top type '%s', using generic\n", type.c_str());
  }
  if (ieq(type, "generic")) {
    Mesh* m = scene.takeMesh(Mesh::createUnitCube());
    avatar->addClothing(m, ClothingTag::Generic, 0.32f, tintRgb);
    return;
  }
  if (!jumperLike) {
    Mesh* m = scene.takeMesh(Mesh::createUnitCube());
    avatar->addClothing(m, ClothingTag::Generic, 0.32f, tintRgb);
    return;
  }
  Mesh* torso = scene.takeMesh(Mesh::createShirtTorsoProxy());
  Mesh* sleeveL = scene.takeMesh(Mesh::createShirtSleeveProxy());
  Mesh* sleeveR = scene.takeMesh(Mesh::createShirtSleeveProxy());
  avatar->addClothing(torso, ClothingTag::Shirt, uniformScale, tintRgb);
  avatar->addClothing(sleeveL, ClothingTag::Shirt, static_cast<int>(AvatarBoneId::LeftArm),
                      Avatar::clothingBindShirtSleeve(uniformScale, false), uniformScale,
                      tintRgb);
  avatar->addClothing(sleeveR, ClothingTag::Shirt, static_cast<int>(AvatarBoneId::RightArm),
                      Avatar::clothingBindShirtSleeve(uniformScale, true), uniformScale,
                      tintRgb);
}

void attachBottomFromSpec(Scene& scene, Avatar* avatar, const std::string& type,
                          const glm::vec3& tintRgb, float uniformScale) {
  if (avatar == nullptr) return;
  if (!ieq(type, "trousers") && !ieq(type, "generic")) {
    std::fprintf(stderr, "[closy] Unknown bottom type '%s', using trousers\n", type.c_str());
  }
  if (ieq(type, "generic")) {
    Mesh* m = scene.takeMesh(Mesh::createUnitCube());
    avatar->addClothing(m, ClothingTag::Generic, 0.4f, tintRgb);
    return;
  }
  Mesh* trHip = scene.takeMesh(Mesh::createTrousersHipProxy());
  Mesh* trLegL = scene.takeMesh(Mesh::createTrousersLegProxy());
  Mesh* trLegR = scene.takeMesh(Mesh::createTrousersLegProxy());
  avatar->addClothing(trHip, ClothingTag::Trousers, uniformScale, tintRgb);
  avatar->addClothing(trLegL, ClothingTag::Trousers, static_cast<int>(AvatarBoneId::LeftLeg),
                      Avatar::clothingBindTrousersLeg(uniformScale), uniformScale, tintRgb);
  avatar->addClothing(trLegR, ClothingTag::Trousers, static_cast<int>(AvatarBoneId::RightLeg),
                      Avatar::clothingBindTrousersLeg(uniformScale), uniformScale, tintRgb);
}

void attachShoesFromSpec(Scene& scene, Avatar* avatar, const std::string& type,
                         const glm::vec3& tintRgb, float uniformScale) {
  if (avatar == nullptr) return;
  if (!ieq(type, "shoes") && !ieq(type, "generic")) {
    std::fprintf(stderr, "[closy] Unknown shoes type '%s', using shoes proxy\n", type.c_str());
  }
  Mesh* sh = scene.takeMesh(Mesh::createShoesProxy());
  avatar->addClothing(sh, ClothingTag::Shoes, uniformScale, tintRgb);
  (void)type;
}

void attachOuterwearPlaceholder(Avatar* avatar, const std::string& type) {
  (void)avatar;
  std::fprintf(stderr, "[closy] outerwear slot not rendered yet (type '%s')\n", type.c_str());
}

void buildOutfitFromDescription(Scene& scene, Avatar& avatar, const OutfitDescription& desc) {
  avatar.clearClothing();
  for (const OutfitItemDesc& it : desc.items) {
    const glm::vec3 tint =
        it.hasColor ? it.color : defaultTintForSlot(it.slot, it.type);
    if (ieq(it.slot, "top")) {
      attachTopFromSpec(scene, &avatar, it.type, tint);
    } else if (ieq(it.slot, "bottom")) {
      attachBottomFromSpec(scene, &avatar, it.type, tint);
    } else if (ieq(it.slot, "shoes")) {
      attachShoesFromSpec(scene, &avatar, it.type, tint);
    } else if (ieq(it.slot, "outerwear")) {
      attachOuterwearPlaceholder(&avatar, it.type);
    } else {
      std::fprintf(stderr, "[closy] Unknown slot '%s', skipping item\n", it.slot.c_str());
    }
  }
}

} // namespace closy
