#include <Closy/Scene.hpp>

#include <Closy/Mesh.hpp>
#include <Closy/Renderer.hpp>

#include <array>
#include <utility>

namespace closy {

Scene::Scene() = default;

Mesh* Scene::takeMesh(std::unique_ptr<Mesh> mesh) {
  Mesh* p = mesh.get();
  ownedMeshes_.push_back(std::move(mesh));
  return p;
}

Avatar* Scene::spawnAvatar() {
  Mesh::MannequinRigArray rig = Mesh::createMannequinRig();
  std::array<Mesh*, kAvatarBodyPartCount> ptrs{};
  for (std::size_t i = 0; i < rig.size(); ++i) {
    ptrs[i] = rig[i].get();
    ownedMeshes_.push_back(std::move(rig[i]));
  }

  auto av = std::make_unique<Avatar>();
  av->setRigMeshes(ptrs);
  av->setPosePreset(AvatarPosePreset::TPose);
  av->update();

  Avatar* raw = av.get();
  avatars_.push_back(std::move(av));
  return raw;
}

void Scene::update() {
  for (auto& a : avatars_) {
    if (a) a->update();
  }
}

void Scene::render(Renderer& renderer, const glm::mat4& view,
                   const glm::mat4& projection) {
  for (auto& a : avatars_) {
    if (a) a->render(renderer, view, projection);
  }
}

} // namespace closy
