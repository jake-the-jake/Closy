#pragma once

#include <Closy/AvatarPose.hpp>
#include <Closy/Bone.hpp>
#include <Closy/ClothingTag.hpp>
#include <Closy/outfit_description.hpp>
#include <Closy/Transform.hpp>
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>

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
  /** When active, `render` emits only a flat white body or garment mask (black background). */
  enum class ClippingMaskPass { Off, BodyWhite, GarmentWhite };

  Avatar();

  /** Assign one sub-mesh per body part (meshes live in bone-local authoring space). */
  void setRigMeshes(const std::array<Mesh*, kAvatarBodyPartCount>& parts);
  const std::array<Mesh*, kAvatarBodyPartCount>& rigMeshes() const { return bodyMeshes_; }

  /** Legacy single mesh path (hidden / not used when rig is set). */
  void setBodyMesh(Mesh* mesh);
  Mesh* bodyMesh() const { return legacyBodyMesh_; }

  void addClothing(Mesh* mesh, ClothingTag tag = ClothingTag::Generic, float uniformScale = 1.f);
  void addClothing(Mesh* mesh, ClothingTag tag, float uniformScale, const glm::vec3& tintRgb);
  /** Explicit anchor (bone index) and offset from that bone; uniformScale scales local after. */
  void addClothing(Mesh* mesh, ClothingTag tag, int anchorBoneIndex,
                   const glm::mat4& localFromAnchor, float uniformScale = 1.f);
  void addClothing(Mesh* mesh, ClothingTag tag, int anchorBoneIndex,
                    const glm::mat4& localFromAnchor, float uniformScale,
                    const glm::vec3& tintRgb);
  /** Mid-torso / upper-pelvis focus in world space for camera framing. */
  glm::vec3 focusPointWorld() const;
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

  /** Dev export: overlay / silhouette contrast modes (see `OutfitDebugRenderMode`). */
  void setDebugRenderMode(OutfitDebugRenderMode m) { debugRenderMode_ = m; }
  OutfitDebugRenderMode debugRenderMode() const { return debugRenderMode_; }

  void setClippingMaskPass(ClippingMaskPass p) { clippingMaskPass_ = p; }
  ClippingMaskPass clippingMaskPass() const { return clippingMaskPass_; }

  /** Dev: post-bind garment transform from export JSON `closy.fit`. */
  void setGarmentFitAdjust(const OutfitGarmentFitAdjust& f) { garmentFit_ = f; }
  const OutfitGarmentFitAdjust& garmentFitAdjust() const { return garmentFit_; }

  static constexpr int boneCount() { return kAvatarBodyPartCount; }

  /** Optional tweak helper: trouser leg mesh bind in leg-bone space (uniform inflate). */
  static glm::mat4 clothingBindTrousersLeg(float uniformScale = 1.f) {
    const float u = uniformScale > 0.f ? uniformScale : 1.f;
    return glm::scale(glm::mat4(1.f), glm::vec3(1.06f * u, 1.04f * u, 1.06f * u));
  }

  /** Shirt sleeve proxy in arm-bone space; negative X scale on `rightArm` matches rig mirroring. */
  static glm::mat4 clothingBindShirtSleeve(float uniformScale = 1.f, bool rightArm = false) {
    const float u = uniformScale > 0.f ? uniformScale : 1.f;
    const float sx = (rightArm ? -1.07f : 1.07f) * u;
    return glm::scale(glm::mat4(1.f), glm::vec3(sx, 1.05f * u, 1.07f * u));
  }

private:
  void buildMinimalSkeleton_();
  void applyPosePresetLocals_(AvatarPosePreset preset);
  static ClothingLayer makeClothingDefaults_(Mesh* mesh, ClothingTag tag,
                                             float uniformScale);

  void renderBodyParts_(Renderer& renderer, const glm::mat4& view,
                        const glm::mat4& projection);
  void renderClothingLayers_(Renderer& renderer, const glm::mat4& view,
                             const glm::mat4& projection);
  void renderClothingFlatWhite_(Renderer& renderer, const glm::mat4& view,
                                const glm::mat4& projection);
  glm::mat4 garmentFitMatrix_(const ClothingLayer& layer) const;

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
  OutfitDebugRenderMode debugRenderMode_ = OutfitDebugRenderMode::Normal;
  ClippingMaskPass clippingMaskPass_ = ClippingMaskPass::Off;
  OutfitGarmentFitAdjust garmentFit_{};
};

} // namespace closy
