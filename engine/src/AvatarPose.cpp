#include <Closy/AvatarPose.hpp>

namespace closy {

const char* avatarPosePresetLabel(AvatarPosePreset p) {
  switch (p) {
  case AvatarPosePreset::TPose:
    return "T-Pose";
  case AvatarPosePreset::APose:
    return "A-Pose";
  case AvatarPosePreset::Relaxed:
    return "Relaxed";
  case AvatarPosePreset::WalkLike:
    return "Walk-like";
  default:
    return "?";
  }
}

} // namespace closy
