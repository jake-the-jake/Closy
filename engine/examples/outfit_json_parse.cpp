#include <Closy/outfit_json_io.hpp>

#include <glm/vec3.hpp>

#include <nlohmann/json.hpp>

#include <algorithm>
#include <cctype>
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

    out.debugRender = OutfitDebugRenderMode::Normal;
    out.clippingThreshold = 0.35f;
    out.clippingVisualization = ClippingVisualizationMode::Hotspot;
    out.clippingShowBaseUnderlay = true;
    out.garmentFit = OutfitGarmentFitAdjust{};

    if (j.contains("closy") && j["closy"].is_object()) {
      const auto& cj = j["closy"];
      if (cj.contains("debug") && cj["debug"].is_object()) {
        const auto& d = cj["debug"];
        bool decided = false;
        if (d.contains("debugMode") && d["debugMode"].is_string()) {
          std::string dm = d["debugMode"].get<std::string>();
          for (auto& ch : dm)
            ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
          if (dm == "silhouette") {
            out.debugRender = OutfitDebugRenderMode::Silhouette;
            decided = true;
          } else if (dm == "overlay") {
            out.debugRender = OutfitDebugRenderMode::Overlay;
            decided = true;
          } else if (dm == "normal") {
            out.debugRender = OutfitDebugRenderMode::Normal;
            decided = true;
          } else if (dm == "clipping") {
            out.debugRender = OutfitDebugRenderMode::ClippingHotspot;
            decided = true;
          }
        }
        if (!decided) {
          if (d.value("showClipping", false)) {
            out.debugRender = OutfitDebugRenderMode::ClippingHotspot;
            decided = true;
          }
        }
        if (!decided) {
          const bool sil = d.value("showSilhouette", false);
          const bool ovl = d.value("showOverlay", false);
          if (sil)
            out.debugRender = OutfitDebugRenderMode::Silhouette;
          else if (ovl)
            out.debugRender = OutfitDebugRenderMode::Overlay;
        }

        if (d.contains("clippingThreshold") && d["clippingThreshold"].is_number()) {
          const float t = d["clippingThreshold"].get<float>();
          out.clippingThreshold = std::max(0.05f, std::min(0.95f, t));
        }
        if (d.contains("clippingVisualization") && d["clippingVisualization"].is_string()) {
          std::string v = d["clippingVisualization"].get<std::string>();
          for (auto& ch : v)
            ch = static_cast<char>(std::tolower(static_cast<unsigned char>(ch)));
          if (v == "binary")
            out.clippingVisualization = ClippingVisualizationMode::Binary;
          else
            out.clippingVisualization = ClippingVisualizationMode::Hotspot;
        }
        if (d.contains("showBaseRenderUnderlay"))
          out.clippingShowBaseUnderlay = d["showBaseRenderUnderlay"].get<bool>();
      }

      if (cj.contains("fit") && cj["fit"].is_object()) {
        const auto& fj = cj["fit"];
        auto numFlat = [&](const char* key, float& dst) {
          if (fj.contains(key) && fj[key].is_number())
            dst = fj[key].get<float>();
        };
        auto readVec3 = [](const nlohmann::json& j, glm::vec3& v) {
          if (j.is_array() && j.size() >= 3) {
            v.x = j.at(0).get<float>();
            v.y = j.at(1).get<float>();
            v.z = j.at(2).get<float>();
          }
        };

        if (fj.contains("global") && fj["global"].is_object()) {
          const auto& g = fj["global"];
          if (g.contains("offset"))
            readVec3(g["offset"], out.garmentFit.globalOffset);
          if (g.contains("scale"))
            readVec3(g["scale"], out.garmentFit.globalScale);
          if (g.contains("inflate") && g["inflate"].is_number())
            out.garmentFit.globalInflate = g["inflate"].get<float>();
        }

        if (fj.contains("regions") && fj["regions"].is_object()) {
          const auto& rj = fj["regions"];
          if (rj.contains("torso") && rj["torso"].is_object()) {
            const auto& t = rj["torso"];
            if (t.contains("offsetZ") && t["offsetZ"].is_number())
              out.garmentFit.torsoOffsetZ = t["offsetZ"].get<float>();
            if (t.contains("inflate") && t["inflate"].is_number())
              out.garmentFit.torsoInflate = t["inflate"].get<float>();
            if (t.contains("scaleY") && t["scaleY"].is_number())
              out.garmentFit.torsoScaleY = std::max(0.04f, t["scaleY"].get<float>());
          }
          if (rj.contains("sleeves") && rj["sleeves"].is_object()) {
            const auto& s = rj["sleeves"];
            if (s.contains("offset"))
              readVec3(s["offset"], out.garmentFit.sleevesOffset);
            if (s.contains("inflate") && s["inflate"].is_number())
              out.garmentFit.sleevesInflate = s["inflate"].get<float>();
          }
          if (rj.contains("waist") && rj["waist"].is_object()) {
            const auto& w = rj["waist"];
            if (w.contains("offsetZ") && w["offsetZ"].is_number())
              out.garmentFit.waistOffsetZ = w["offsetZ"].get<float>();
            if (w.contains("tighten") && w["tighten"].is_number())
              out.garmentFit.waistTighten = w["tighten"].get<float>();
          }
          if (rj.contains("hem") && rj["hem"].is_object()) {
            const auto& h = rj["hem"];
            if (h.contains("offsetY") && h["offsetY"].is_number())
              out.garmentFit.hemOffsetY = h["offsetY"].get<float>();
          }
        }

        numFlat("offsetX", out.garmentFit.globalOffset.x);
        numFlat("offsetY", out.garmentFit.globalOffset.y);
        numFlat("offsetZ", out.garmentFit.globalOffset.z);
        numFlat("scaleX", out.garmentFit.globalScale.x);
        numFlat("scaleY", out.garmentFit.globalScale.y);
        numFlat("scaleZ", out.garmentFit.globalScale.z);
        numFlat("inflate", out.garmentFit.globalInflate);
        numFlat("shrinkwrapStrength", out.garmentFit.shrinkwrapStrength);
        numFlat("bodyOffsetBias", out.garmentFit.bodyOffsetBias);
        numFlat("torsoOffsetZ", out.garmentFit.torsoOffsetZ);
        numFlat("sleeveOffset", out.garmentFit.legacySleeveOffsetY);
        numFlat("waistAdjust", out.garmentFit.legacyWaistAdjustY);

        out.garmentFit.globalScale.x = std::max(0.04f, out.garmentFit.globalScale.x);
        out.garmentFit.globalScale.y = std::max(0.04f, out.garmentFit.globalScale.y);
        out.garmentFit.globalScale.z = std::max(0.04f, out.garmentFit.globalScale.z);
      }
    }
  } catch (const std::exception& e) {
    err = e.what();
    return false;
  }

  return true;
}

} // namespace closy
