#pragma once

#include <glm/vec3.hpp>

#include <string>
#include <vector>

namespace closy {

/** Parsed outfit file (`--outfit` JSON). CLI may override pose/size/camera after load. */
struct OutfitItemDesc {
  std::string slot; // top | bottom | shoes | outerwear
  std::string type; // jumper | shirt | trousers | shoes | generic
  bool hasColor = false;
  glm::vec3 color{0.f};
};

struct OutfitDescription {
  std::string pose = "relaxed";
  int width = 1024;
  int height = 1024;
  /** three_quarter | front | side */
  std::string camera = "three_quarter";
  std::vector<OutfitItemDesc> items;
};

/** Same pieces/colors as legacy demo (no JSON needed). Implemented in `outfit_builder.cpp`. */
OutfitDescription defaultDemoOutfitDescription();

} // namespace closy
