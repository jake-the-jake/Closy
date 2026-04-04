#pragma once

#include <glm/glm.hpp>

namespace closy {

class Mesh;

/**
 * Renderer facade used by Avatar / Scene.
 * Concrete GPU backend (e.g. GlRenderer) implements upload + draw.
 */
class Renderer {
public:
  virtual ~Renderer() = default;

  /** Optional per-draw albedo hint for mesh passes (no-op for backends that ignore it). */
  virtual void setMeshColor(const glm::vec3& /*rgb*/) {}

  virtual void renderMesh(const Mesh& mesh, const glm::mat4& model,
                          const glm::mat4& view, const glm::mat4& projection) = 0;

  /** Debug: line in world space (e.g. bone chains). */
  virtual void drawLine(const glm::vec3& aWorld, const glm::vec3& bWorld,
                        const glm::mat4& view, const glm::mat4& projection,
                        const glm::vec4& rgba) = 0;

  virtual void beginFrame(const glm::vec4& clearRgbDepth = {0.08f, 0.09f, 0.11f, 1.f}) = 0;
  virtual void endFrame() = 0;
};

} // namespace closy
