#include <Closy/Mesh.hpp>

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>

#include <cstddef>
#include <initializer_list>
#include <tuple>

namespace closy {
namespace {

void appendCube(std::vector<float>& v, std::vector<std::uint32_t>& idx,
                const glm::mat4& transform) {
  const std::uint32_t base = static_cast<std::uint32_t>(v.size() / 6);
  const glm::vec3 corners[8] = {
      {-1, -1, 1}, {1, -1, 1}, {1, 1, 1}, {-1, 1, 1},
      {-1, -1, -1}, {1, -1, -1}, {1, 1, -1}, {-1, 1, -1},
  };
  const int faces[6][4] = {
      {0, 1, 2, 3}, {5, 4, 7, 6}, {4, 0, 3, 7}, {1, 5, 6, 2}, {3, 2, 6, 7}, {4, 5, 1, 0},
  };
  const glm::vec3 faceN[6] = {
      {0, 0, 1}, {0, 0, -1}, {-1, 0, 0}, {1, 0, 0}, {0, 1, 0}, {0, -1, 0},
  };

  for (int f = 0; f < 6; ++f) {
    const glm::vec3 fn = faceN[f];
    for (int k = 0; k < 4; ++k) {
      const glm::vec4 wp = transform * glm::vec4(corners[faces[f][k]], 1.f);
      v.push_back(wp.x);
      v.push_back(wp.y);
      v.push_back(wp.z);
      v.push_back(fn.x);
      v.push_back(fn.y);
      v.push_back(fn.z);
    }
    const std::uint32_t b = base + static_cast<std::uint32_t>(f * 4);
    idx.push_back(b);
    idx.push_back(b + 1);
    idx.push_back(b + 2);
    idx.push_back(b);
    idx.push_back(b + 2);
    idx.push_back(b + 3);
  }
}

glm::mat4 box(float sx, float sy, float sz, glm::vec3 center) {
  glm::mat4 t = glm::translate(glm::mat4(1.f), center);
  glm::mat4 s = glm::scale(glm::mat4(1.f), {sx * 0.5f, sy * 0.5f, sz * 0.5f});
  return t * s;
}

} // namespace

std::unique_ptr<Mesh> Mesh::createUnitCube() {
  auto m = std::make_unique<Mesh>();
  appendCube(m->interleavedVertices, m->indices, glm::mat4(1.f));
  return m;
}

Mesh::MannequinRigArray Mesh::createMannequinRig() {
  MannequinRigArray rig{};

  auto make = [](std::initializer_list<std::tuple<glm::vec3, glm::vec3>> parts) {
    auto m = std::make_unique<Mesh>();
    for (const auto& pr : parts) {
      const glm::vec3& c = std::get<0>(pr);
      const glm::vec3& sz = std::get<1>(pr);
      appendCube(m->interleavedVertices, m->indices, box(sz.x, sz.y, sz.z, c));
    }
    return m;
  };

  // Pelvis (root bone space): wider hips, shallow depth
  rig[0] = make({
      {{0.f, 0.06f, 0.f}, {0.40f, 0.15f, 0.24f}},
  });

  // Torso (spine space): taller chest, subtle shoulder taper via second box
  rig[1] = make({
      {{0.f, 0.29f, 0.f}, {0.38f, 0.52f, 0.21f}},
      {{0.f, 0.48f, 0.f}, {0.46f, 0.12f, 0.23f}},
  });

  // Head (head bone space)
  rig[2] = make({
      {{0.f, 0.12f, 0.f}, {0.20f, 0.23f, 0.19f}},
  });

  // Left arm (+X), thicker / longer
  rig[3] = make({
      {{0.36f, 0.01f, 0.f}, {0.72f, 0.15f, 0.15f}},
  });

  // Right arm (−X)
  rig[4] = make({
      {{-0.36f, 0.01f, 0.f}, {0.72f, 0.15f, 0.15f}},
  });

  // Legs (−Y), longer slightly thicker
  rig[5] = make({
      {{0.f, -0.38f, 0.f}, {0.16f, 0.78f, 0.15f}},
  });
  rig[6] = make({
      {{0.f, -0.38f, 0.f}, {0.16f, 0.78f, 0.15f}},
  });

  return rig;
}

std::unique_ptr<Mesh> Mesh::createMannequin() {
  auto m = std::make_unique<Mesh>();
  const MannequinRigArray rig = createMannequinRig();
  std::uint32_t vbase = 0;
  for (std::size_t i = 0; i < rig.size(); ++i) {
    if (!rig[i]) continue;
    const auto& srcV = rig[i]->interleavedVertices;
    const auto& srcI = rig[i]->indices;
    m->interleavedVertices.insert(m->interleavedVertices.end(), srcV.begin(), srcV.end());
    for (std::uint32_t id : srcI)
      m->indices.push_back(vbase + id);
    vbase += static_cast<std::uint32_t>(srcV.size() / 6);
  }
  return m;
}

std::unique_ptr<Mesh> Mesh::createShirtProxy() {
  auto m = std::make_unique<Mesh>();
  // Spine-local: clearer shoulders + torso block
  appendCube(m->interleavedVertices, m->indices,
             box(0.40f, 0.56f, 0.26f, {0.f, 0.30f, 0.01f}));
  appendCube(m->interleavedVertices, m->indices,
             box(0.50f, 0.14f, 0.16f, {0.26f, 0.44f, 0.f}));
  appendCube(m->interleavedVertices, m->indices,
             box(0.50f, 0.14f, 0.16f, {-0.26f, 0.44f, 0.f}));
  return m;
}

std::unique_ptr<Mesh> Mesh::createTrousersProxy() {
  auto m = std::make_unique<Mesh>();
  // Root-local: seat + legs + waist band
  appendCube(m->interleavedVertices, m->indices,
             box(0.38f, 0.12f, 0.26f, {0.f, -0.02f, 0.f}));
  appendCube(m->interleavedVertices, m->indices,
             box(0.18f, 0.74f, 0.18f, {0.11f, -0.44f, 0.f}));
  appendCube(m->interleavedVertices, m->indices,
             box(0.18f, 0.74f, 0.18f, {-0.11f, -0.44f, 0.f}));
  return m;
}

std::unique_ptr<Mesh> Mesh::createShoesProxy() {
  auto m = std::make_unique<Mesh>();
  appendCube(m->interleavedVertices, m->indices,
             box(0.15f, 0.09f, 0.28f, {0.12f, -0.86f, 0.05f}));
  appendCube(m->interleavedVertices, m->indices,
             box(0.15f, 0.09f, 0.28f, {-0.12f, -0.86f, 0.05f}));
  return m;
}

} // namespace closy
