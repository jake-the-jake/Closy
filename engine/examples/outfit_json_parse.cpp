#include <Closy/outfit_json_io.hpp>

#include <glm/vec3.hpp>

#include <nlohmann/json.hpp>

#include <fstream>
#include <string>

namespace closy {
namespace {

bool readColor(const nlohmann::json& j, glm::vec3& v) {
  if (!j.is_array() || j.size() < 3) return false;
  v.x = j.at(0).get<float>();
  v.y = j.at(1).get<float>();
  v.z = j.at(2).get<float>();
  return true;
}

} // namespace

bool parseOutfitJsonFile(const char* path, OutfitDescription& out, std::string& err) {
  if (path == nullptr) {
    err = "Null path";
    return false;
  }
  std::ifstream f(path);
  if (!f) {
    err = "Failed to open outfit file";
    return false;
  }

  nlohmann::json j;
  try {
    f >> j;
  } catch (const std::exception& e) {
    err = e.what();
    return false;
  } catch (...) {
    err = "JSON parse error";
    return false;
  }

  try {
    if (j.contains("pose") && j["pose"].is_string())
      out.pose = j["pose"].get<std::string>();
    if (j.contains("width") && j["width"].is_number_integer())
      out.width = j["width"].get<int>();
    if (j.contains("height") && j["height"].is_number_integer())
      out.height = j["height"].get<int>();
    if (j.contains("camera") && j["camera"].is_string())
      out.camera = j["camera"].get<std::string>();

    out.items.clear();
    if (j.contains("items") && j["items"].is_array()) {
      for (const auto& el : j["items"]) {
        OutfitItemDesc it;
        if (el.contains("slot") && el["slot"].is_string())
          it.slot = el["slot"].get<std::string>();
        if (el.contains("type") && el["type"].is_string())
          it.type = el["type"].get<std::string>();
        if (el.contains("color")) {
          glm::vec3 c;
          if (readColor(el["color"], c)) {
            it.color = c;
            it.hasColor = true;
          }
        }
        out.items.push_back(std::move(it));
      }
    }
  } catch (const std::exception& e) {
    err = e.what();
    return false;
  }

  return true;
}

} // namespace closy
