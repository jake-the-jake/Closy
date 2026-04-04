#include <Closy/Avatar.hpp>
#include <Closy/AvatarPose.hpp>
#include <Closy/Mesh.hpp>
#include <Closy/Scene.hpp>

#include <cassert>
#include <cstdio>

int main() {
  closy::Scene scene;
  closy::Avatar* avatar = scene.spawnAvatar();

  assert(closy::Avatar::boneCount() == 7);
  assert(avatar->bones().size() == static_cast<std::size_t>(closy::Avatar::boneCount()));
  assert(avatar->rigMeshes()[static_cast<std::size_t>(closy::AvatarBodyPart::Pelvis)] != nullptr);
  assert(avatar->bodyMesh() == nullptr);

  const closy::AvatarPosePreset presets[] = {
      closy::AvatarPosePreset::TPose,
      closy::AvatarPosePreset::APose,
      closy::AvatarPosePreset::Relaxed,
      closy::AvatarPosePreset::WalkLike,
  };
  for (closy::AvatarPosePreset pr : presets) {
    avatar->setPosePreset(pr);
    assert(avatar->posePreset() == pr);
    avatar->update();
  }

  closy::Mesh* shirt = scene.takeMesh(closy::Mesh::createShirtProxy());
  closy::Mesh* trousers = scene.takeMesh(closy::Mesh::createTrousersProxy());
  avatar->addClothing(shirt, closy::ClothingTag::Shirt, 1.03f);
  avatar->addClothing(trousers, closy::ClothingTag::Trousers, 1.02f);
  avatar->update();

  assert(avatar->removeClothing(shirt));
  assert(avatar->removeClothing(trousers));
  avatar->clearClothing();

  closy::Mesh* cube = scene.takeMesh(closy::Mesh::createUnitCube());
  avatar->addClothing(cube, closy::ClothingTag::Generic, 1.f);
  assert(avatar->removeClothing(cube));

  std::printf("avatar_smoke: ok (%s)\n", closy::avatarPosePresetLabel(avatar->posePreset()));
  return 0;
}
