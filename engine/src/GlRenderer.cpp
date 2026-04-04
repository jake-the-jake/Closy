#include <Closy/GlRenderer.hpp>
#include <Closy/Mesh.hpp>

#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/type_ptr.hpp>

#include "gl_procs.hpp"

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>

namespace closy {
namespace {

constexpr unsigned kGL_TRIANGLES = 0x0004;
constexpr unsigned kGL_LINES = 0x0001;
constexpr unsigned kGL_DEPTH_TEST = 0x0B71;
constexpr unsigned kGL_LESS = 0x0201;
constexpr unsigned kGL_COLOR_BUFFER_BIT = 0x00004000;
constexpr unsigned kGL_DEPTH_BUFFER_BIT = 0x00000100;
constexpr unsigned kGL_ARRAY_BUFFER = 0x8892;
constexpr unsigned kGL_ELEMENT_ARRAY_BUFFER = 0x8893;
constexpr unsigned kGL_STATIC_DRAW = 0x88E4;
constexpr unsigned kGL_FLOAT = 0x1406;
constexpr unsigned kGL_UNSIGNED_INT = 0x1405;
constexpr unsigned kGL_FALSE_U8 = 0;
constexpr unsigned kGL_VERTEX_SHADER = 0x8B31;
constexpr unsigned kGL_FRAGMENT_SHADER = 0x8B30;
constexpr unsigned kGL_COMPILE_STATUS = 0x8B81;
constexpr unsigned kGL_LINK_STATUS = 0x8B82;
constexpr unsigned kGL_FILL = 0x1B02;
constexpr unsigned kGL_FRONT_AND_BACK = 0x0408;

static const char* kVsMesh = R"GLSL(
#version 330 core
layout (location = 0) in vec3 aPos;
layout (location = 1) in vec3 aN;
uniform mat4 uMVP;
out vec3 vWorldN;
void main() {
  vWorldN = aN;
  gl_Position = uMVP * vec4(aPos, 1.0);
}
)GLSL";

static const char* kFsMesh = R"GLSL(
#version 330 core
in vec3 vWorldN;
uniform vec3 uColor;
out vec4 FragColor;
void main() {
  vec3 L = normalize(vec3(0.35, 0.85, 0.45));
  float nd = max(dot(normalize(vWorldN), L), 0.12);
  FragColor = vec4(uColor * nd, 1.0);
}
)GLSL";

static const char* kVsLine = R"GLSL(
#version 330 core
layout (location = 0) in vec3 aPos;
uniform mat4 uMVP;
void main() {
  gl_Position = uMVP * vec4(aPos, 1.0);
}
)GLSL";

static const char* kFsLine = R"GLSL(
#version 330 core
uniform vec4 uColor;
out vec4 FragColor;
void main() {
  FragColor = uColor;
}
)GLSL";

} // namespace

GlRenderer::GlRenderer(GlProcs& gl) : gl_(gl) {
  meshProgram_ = linkProgram_(compileShader_(kGL_VERTEX_SHADER, kVsMesh),
                              compileShader_(kGL_FRAGMENT_SHADER, kFsMesh));
  locMvp_ = gl_.getUniformLocation(meshProgram_, "uMVP");
  locColor_ = gl_.getUniformLocation(meshProgram_, "uColor");

  lineProgram_ = linkProgram_(compileShader_(kGL_VERTEX_SHADER, kVsLine),
                              compileShader_(kGL_FRAGMENT_SHADER, kFsLine));
  lineLocMvp_ = gl_.getUniformLocation(lineProgram_, "uMVP");
  lineLocColor_ = gl_.getUniformLocation(lineProgram_, "uColor");

  gl_.genBuffers(1, &lineVbo_);
  gl_.genVertexArrays(1, &lineVao_);
  gl_.bindVertexArray(lineVao_);
  gl_.bindBuffer(kGL_ARRAY_BUFFER, lineVbo_);
  gl_.vertexAttribPointer(0, 3, kGL_FLOAT, kGL_FALSE_U8,
                          static_cast<int>(sizeof(float) * 3), nullptr);
  gl_.enableVertexAttribArray(0);
  gl_.bindVertexArray(0);
}

GlRenderer::~GlRenderer() {
  for (auto& e : gpu_) {
    if (e.second.vao != 0) {
      gl_.deleteVertexArrays(1, &e.second.vao);
    }
    if (e.second.vbo != 0) {
      gl_.deleteBuffers(1, &e.second.vbo);
    }
    if (e.second.ebo != 0) {
      gl_.deleteBuffers(1, &e.second.ebo);
    }
  }
  gpu_.clear();
  if (lineVao_ != 0) gl_.deleteVertexArrays(1, &lineVao_);
  if (lineVbo_ != 0) gl_.deleteBuffers(1, &lineVbo_);
  if (meshProgram_ != 0) gl_.deleteProgram(meshProgram_);
  if (lineProgram_ != 0) gl_.deleteProgram(lineProgram_);
}

unsigned GlRenderer::compileShader_(unsigned type, const char* src) {
  const unsigned s = gl_.createShader(type);
  const char* ptr = src;
  const int len = static_cast<int>(std::strlen(src));
  gl_.shaderSource(s, 1, &ptr, &len);
  gl_.compileShader(s);
  int ok = 0;
  gl_.getShaderiv(s, kGL_COMPILE_STATUS, &ok);
  if (ok == 0) {
    char log[1024];
    gl_.getShaderInfoLog(s, static_cast<int>(sizeof(log)), nullptr, log);
    std::fprintf(stderr, "[closy] Shader compile: %s\n", log);
  }
  return s;
}

unsigned GlRenderer::linkProgram_(unsigned vs, unsigned fs) {
  const unsigned p = gl_.createProgram();
  gl_.attachShader(p, vs);
  gl_.attachShader(p, fs);
  gl_.linkProgram(p);
  gl_.deleteShader(vs);
  gl_.deleteShader(fs);
  int ok = 0;
  gl_.getProgramiv(p, kGL_LINK_STATUS, &ok);
  if (ok == 0) {
    char log[1024];
    gl_.getProgramInfoLog(p, static_cast<int>(sizeof(log)), nullptr, log);
    std::fprintf(stderr, "[closy] Program link: %s\n", log);
  }
  return p;
}

void GlRenderer::ensureMeshUploaded_(const Mesh& mesh) {
  if (gpu_.count(&mesh) != 0) return;
  GpuMesh g{};
  gl_.genVertexArrays(1, &g.vao);
  gl_.genBuffers(1, &g.vbo);
  gl_.genBuffers(1, &g.ebo);

  gl_.bindVertexArray(g.vao);
  gl_.bindBuffer(kGL_ARRAY_BUFFER, g.vbo);
  gl_.bufferData(kGL_ARRAY_BUFFER,
                 static_cast<std::ptrdiff_t>(mesh.interleavedVertices.size() *
                                              sizeof(float)),
                 mesh.interleavedVertices.empty() ? nullptr
                                                  : mesh.interleavedVertices.data(),
                 kGL_STATIC_DRAW);
  gl_.bindBuffer(kGL_ELEMENT_ARRAY_BUFFER, g.ebo);
  gl_.bufferData(kGL_ELEMENT_ARRAY_BUFFER,
                 static_cast<std::ptrdiff_t>(mesh.indices.size() * sizeof(std::uint32_t)),
                 mesh.indices.empty() ? nullptr : mesh.indices.data(), kGL_STATIC_DRAW);

  const int stride = static_cast<int>(6 * sizeof(float));
  gl_.vertexAttribPointer(0, 3, kGL_FLOAT, kGL_FALSE_U8, stride, nullptr);
  gl_.enableVertexAttribArray(0);
  gl_.vertexAttribPointer(1, 3, kGL_FLOAT, kGL_FALSE_U8, stride,
                          reinterpret_cast<void*>(static_cast<std::uintptr_t>(3 * sizeof(float))));
  gl_.enableVertexAttribArray(1);

  gl_.bindVertexArray(0);
  gpu_[&mesh] = g;
}

void GlRenderer::renderMesh(const Mesh& mesh, const glm::mat4& model,
                            const glm::mat4& view, const glm::mat4& projection) {
  if (mesh.indices.empty()) return;
  ensureMeshUploaded_(mesh);

  const glm::mat4 mvp = projection * view * model;
  gl_.useProgram(meshProgram_);
  gl_.uniformMatrix4fv(locMvp_, 1, kGL_FALSE_U8, glm::value_ptr(mvp));
  gl_.uniform3fv(locColor_, 1, glm::value_ptr(meshRgb_));

  gl_.polygonMode(kGL_FRONT_AND_BACK, kGL_FILL);
  const GpuMesh& g = gpu_[&mesh];
  gl_.bindVertexArray(g.vao);
  gl_.drawElements(kGL_TRIANGLES, static_cast<int>(mesh.indices.size()),
                   kGL_UNSIGNED_INT, nullptr);
  gl_.bindVertexArray(0);
}

void GlRenderer::drawLine(const glm::vec3& aWorld, const glm::vec3& bWorld,
                          const glm::mat4& view, const glm::mat4& projection,
                          const glm::vec4& rgba) {
  const float verts[6] = {aWorld.x, aWorld.y, aWorld.z, bWorld.x, bWorld.y, bWorld.z};
  const glm::mat4 mvp = projection * view * glm::mat4(1.f);

  gl_.useProgram(lineProgram_);
  gl_.uniformMatrix4fv(lineLocMvp_, 1, kGL_FALSE_U8, glm::value_ptr(mvp));
  gl_.uniform4fv(lineLocColor_, 1, glm::value_ptr(rgba));

  gl_.lineWidth(2.f);
  gl_.bindVertexArray(lineVao_);
  gl_.bindBuffer(kGL_ARRAY_BUFFER, lineVbo_);
  gl_.bufferData(kGL_ARRAY_BUFFER, static_cast<std::ptrdiff_t>(sizeof(verts)), verts,
                 kGL_STATIC_DRAW);
  gl_.drawArrays(kGL_LINES, 0, 2);
  gl_.bindVertexArray(0);
}

void GlRenderer::beginFrame(const glm::vec4& clearRgbDepth) {
  gl_.enable(kGL_DEPTH_TEST);
  gl_.depthFunc(kGL_LESS);
  gl_.clearColor(clearRgbDepth.r, clearRgbDepth.g, clearRgbDepth.b, clearRgbDepth.a);
  gl_.clear(kGL_COLOR_BUFFER_BIT | kGL_DEPTH_BUFFER_BIT);
}

void GlRenderer::endFrame() {}

} // namespace closy
