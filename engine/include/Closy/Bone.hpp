#pragma once

#include <glm/glm.hpp>
#include <string>

namespace closy {

struct Bone {
  std::string name;
  glm::mat4 localTransform{1.f};
  glm::mat4 worldTransform{1.f};
  /** Index into the same bone vector, or -1 for root. */
  int parentIndex = -1;
};

} // namespace closy
