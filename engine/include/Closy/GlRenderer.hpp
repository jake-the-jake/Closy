#pragma once

#include <Closy/Renderer.hpp>
#include <Closy/gl_procs.hpp>

#include <unordered_map>

namespace closy {

class GlRenderer final : public Renderer {
public:
  explicit GlRenderer(GlProcs& gl);
  ~GlRenderer() override;

  void renderMesh(const Mesh& mesh, const glm::mat4& model, const glm::mat4& view,
                   const glm::mat4& projection) override;

  void drawLine(const glm::vec3& aWorld, const glm::vec3& bWorld, const glm::mat4& view,
                const glm::mat4& projection, const glm::vec4& rgba) override;

  void beginFrame(const glm::vec4& clearRgbDepth = {0.08f, 0.09f, 0.11f,
                                                   1.f}) override;
  void endFrame() override;

  void setMeshColor(const glm::vec3& rgb) override { meshRgb_ = rgb; }

private:
  struct GpuMesh {
    unsigned vao = 0;
    unsigned vbo = 0;
    unsigned ebo = 0;
  };

  void ensureMeshUploaded_(const Mesh& mesh);
  unsigned compileShader_(unsigned type, const char* src);
  unsigned linkProgram_(unsigned vs, unsigned fs);

  GlProcs& gl_;
  std::unordered_map<const Mesh*, GpuMesh> gpu_;

  unsigned meshProgram_ = 0;
  int locMvp_ = -1;
  int locColor_ = -1;

  unsigned lineProgram_ = 0;
  int lineLocMvp_ = -1;
  int lineLocColor_ = -1;
  unsigned lineVao_ = 0;
  unsigned lineVbo_ = 0;

  glm::vec3 meshRgb_{0.82f, 0.78f, 0.72f};
};

} // namespace closy
