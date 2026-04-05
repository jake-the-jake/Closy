#pragma once

#include <glm/gtc/matrix_transform.hpp>
#include <glm/mat4x4.hpp>
#include <glm/vec3.hpp>

#include <cctype>
#include <cstddef>
#include <cmath>
#include <cstring>
#include <string>

namespace closy {

/** Default export orbit (pleasant 3/4, full-figure framing). */
inline constexpr float kAvatarExportYaw = 0.52f;
inline constexpr float kAvatarExportPitch = 0.13f;
inline constexpr float kAvatarExportDistance = 5.75f;
inline constexpr float kAvatarExportFovDeg = 42.f;

enum class AvatarExportCameraPreset : int { ThreeQuarter, Front, Side };

inline void exportCameraAngles(AvatarExportCameraPreset preset, float& yaw, float& pitch) {
  switch (preset) {
  case AvatarExportCameraPreset::ThreeQuarter:
    yaw = kAvatarExportYaw;
    pitch = kAvatarExportPitch;
    break;
  case AvatarExportCameraPreset::Front:
    yaw = 0.f;
    pitch = 0.12f;
    break;
  case AvatarExportCameraPreset::Side:
    yaw = 1.57079633f;
    pitch = 0.12f;
    break;
  }
}

/** Accepts: three_quarter, three-quarter, front, side. */
inline bool avatarExportCameraFromJsonString(const std::string& s,
                                             AvatarExportCameraPreset& out) {
  std::string t;
  t.reserve(s.size());
  for (char c : s) {
    if (c == '-' || c == '/')
      t.push_back('_');
    else
      t.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
  }
  if (t == "three_quarter" || t == "3_4" || t == "threequarter")
    out = AvatarExportCameraPreset::ThreeQuarter;
  else if (t == "front")
    out = AvatarExportCameraPreset::Front;
  else if (t == "side")
    out = AvatarExportCameraPreset::Side;
  else
    return false;
  return true;
}

/** Suggested directory for app-ingested previews (caller creates it if needed). */
inline constexpr const char* kDefaultAvatarPreviewDir = "closy_avatar_preview";

inline glm::mat4 avatarExportView(const glm::vec3& focusWorld, float yaw, float pitch,
                                  float distance) {
  const float x = std::cos(yaw) * std::cos(pitch) * distance;
  const float y = std::sin(pitch) * distance;
  const float z = std::sin(yaw) * std::cos(pitch) * distance;
  const glm::vec3 eye = focusWorld + glm::vec3(x, y, z);
  return glm::lookAt(eye, focusWorld, glm::vec3(0.f, 1.f, 0.f));
}

inline glm::mat4 avatarExportProjection(float aspect, float fovyDeg = kAvatarExportFovDeg) {
  return glm::perspective(glm::radians(fovyDeg), aspect, 0.1f, 100.f);
}

/** Insert `_suffix` before `.png` in `path` (buffer must hold result). Returns false if too long. */
inline bool pngPathWithSuffix(const char* path, const char* suffix, char* out, std::size_t outSz) {
  const std::size_t n = std::strlen(path);
  const std::size_t sufLen = std::strlen(suffix);
  if (n >= 4 && std::strcmp(path + n - 4, ".png") == 0) {
    const std::size_t stem = n - 4;
    if (stem + sufLen + 4 + 1 > outSz) return false;
    std::memcpy(out, path, stem);
    std::memcpy(out + stem, suffix, sufLen);
    std::memcpy(out + stem + sufLen, ".png", 5);
    return true;
  }
  if (n + sufLen + 1 > outSz) return false;
  std::memcpy(out, path, n);
  std::memcpy(out + n, suffix, sufLen + 1);
  return true;
}

} // namespace closy
