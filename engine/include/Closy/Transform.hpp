#pragma once

#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <glm/gtc/quaternion.hpp>

namespace closy {

/** TRS model transform; combines into a single model matrix for rendering. */
struct Transform {
  glm::vec3 position{0.f};
  glm::quat rotation{1.f, 0.f, 0.f, 0.f};
  glm::vec3 scale{1.f};

  glm::mat4 toMat4() const {
    const glm::mat4 T = glm::translate(glm::mat4(1.f), position);
    const glm::mat4 R = glm::mat4_cast(rotation);
    const glm::mat4 S = glm::scale(glm::mat4(1.f), scale);
    return T * R * S;
  }

  void setEulerDegrees(const glm::vec3& deg) {
    const glm::vec3 r = glm::radians(deg);
    rotation = glm::quat(r);
  }
};

} // namespace closy
