#pragma once

#include <Closy/AvatarPose.hpp>
#include <Closy/Bone.hpp>
#include <Closy/ClothingTag.hpp>
#include <Closy/Transform.hpp>
#include <glm/glm.hpp>

#include <array>
#include <cstddef>
#include <vector>

namespace closy {

class Mesh;
class Renderer;

/** Indices match the hardcoded skeleton (root → spine → head; arms on spine; legs on root). */
enum class AvatarBoneId : int {
  Root = 0,
  Spine,
  Head,
  LeftArm,
  RightArm,
  LeftLeg,
  RightLeg,
};

constexpr int kAvatarBodyPartCount = 7;

/** Pelvis, torso, head, limbs — same order as `AvatarBoneId` for rendering. */
enum class AvatarBodyPart : int {
  Pelvis = 0,
  Torso,
  Head,
  LeftArm,
  RightArm,
  LeftLeg,
  RightLeg,
};

struct ClothingLayer {
  Mesh* mesh = nullptr;
  ClothingTag tag = ClothingTag::Generic;
  int anchorBoneIndex = static_cast<int>(AvatarBoneId::Root);
  /** dress(model) = anchorWorld * localFromAnchor */
  glm::mat4 localFromAnchor{1.f};
  glm::vec3 tintRgb{0.5f, 0.55f, 0.85f};
};

class Avatar {
public:
  Avatar();

  /** Assign one sub-mesh per body part (meshes live in bone-local authoring space). */
  void setRigMeshes(const std::array<Mesh*, kAvatarBodyPartCount>& parts);
  const std::array<Mesh*, kAvatarBodyPartCount>& rigMeshes() const { return bodyMeshes_; }

  /** Legacy single mesh path (hidden / not used when rig is set). */
  void setBodyMesh(Mesh* mesh);
  Mesh* bodyMesh() const { return legacyBodyMesh_; }

  void addClothing(Mesh* mesh, ClothingTag tag = ClothingTag::Generic, float uniformScale = 1.f);
  bool removeClothing(const Mesh* mesh);
  void clearClothing();

  void setTransform(const Transform& t) { transform_ = t; }
  Transform& transform() { return transform_; }
  const Transform& transform() const { return transform_; }

  void setPosePreset(AvatarPosePreset preset);
  AvatarPosePreset posePreset() const { return currentPose_; }

  /** @deprecated Use setPosePreset(AvatarPosePreset::TPose). */
  void setTPose();

  void update();

  void render(Renderer& renderer, const glm::mat4& view,
              const glm::mat4& projection);

  const std::vector<Bone>& bones() const { return bones_; }

  void setShowSkeletonDebug(bool v) { showSkeletonDebug_ = v; }
  bool showSkeletonDebug() const { return showSkeletonDebug_; }

  static constexpr int boneCount() { return kAvatarBodyPartCount; }

private:
  void buildMinimalSkeleton_();
  void applyPosePresetLocals_(AvatarPosePreset preset);
  static ClothingLayer makeClothingDefaults_(Mesh* mesh, ClothingTag tag,
                                             float uniformScale);

  void renderBodyParts_(Renderer& renderer, const glm::mat4& view,
                        const glm::mat4& projection);
  void renderClothingLayers_(Renderer& renderer, const glm::mat4& view,
                             const glm::mat4& projection);

  std::array<Mesh*, kAvatarBodyPartCount> bodyMeshes_{};
  Mesh* legacyBodyMesh_ = nullptr;
  bool useRigMeshes_ = false;

  std::vector<ClothingLayer> clothing_;
  Transform transform_;
  std::vector<Bone> bones_;
  std::array<glm::mat4, kAvatarBodyPartCount> bindLocal_{};
  std::array<glm::mat4, kAvatarBodyPartCount> poseLocal_{};
  AvatarPosePreset currentPose_ = AvatarPosePreset::TPose;
  bool showSkeletonDebug_ = false;
};

} // namespace closy
