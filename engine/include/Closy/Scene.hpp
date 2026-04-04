#pragma once

#include <Closy/Avatar.hpp>
#include <Closy/Mesh.hpp>

#include <glm/glm.hpp>

#include <memory>
#include <vector>

namespace closy {

class Mesh;
class Renderer;

class Scene {
public:
  Scene();

  /** Create avatar with procedural mannequin mesh (owned by scene). */
  Avatar* spawnAvatar();

  /** Transfer mesh ownership to the scene; returns raw pointer for attachment. */
  Mesh* takeMesh(std::unique_ptr<Mesh> mesh);

  void update();
  void render(Renderer& renderer, const glm::mat4& view,
              const glm::mat4& projection);

  const std::vector<std::unique_ptr<Avatar>>& avatars() const { return avatars_; }

private:
  std::vector<std::unique_ptr<Avatar>> avatars_;
  std::vector<std::unique_ptr<Mesh>> ownedMeshes_;
};

} // namespace closy
