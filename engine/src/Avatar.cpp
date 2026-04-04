#include <Closy/Avatar.hpp>
#include <Closy/Mesh.hpp>
#include <Closy/Renderer.hpp>

#include <glm/gtc/matrix_transform.hpp>

#include <algorithm>
#include <cmath>

namespace closy {

namespace {

constexpr int kRoot = static_cast<int>(AvatarBoneId::Root);
constexpr int kSpine = static_cast<int>(AvatarBoneId::Spine);
constexpr int kHead = static_cast<int>(AvatarBoneId::Head);
constexpr int kLeftArm = static_cast<int>(AvatarBoneId::LeftArm);
constexpr int kRightArm = static_cast<int>(AvatarBoneId::RightArm);
constexpr int kLeftLeg = static_cast<int>(AvatarBoneId::LeftLeg);
constexpr int kRightLeg = static_cast<int>(AvatarBoneId::RightLeg);

glm::vec3 worldPos(const glm::mat4& m) { return glm::vec3(m[3]); }

int clampBoneIndex(int idx) {
  return std::clamp(idx, 0, kAvatarBodyPartCount - 1);
}

} // namespace

Avatar::Avatar() { buildMinimalSkeleton_(); }

void Avatar::buildMinimalSkeleton_() {
  bones_.resize(kAvatarBodyPartCount);
  bones_[kRoot] = {"root", glm::mat4(1.f), glm::mat4(1.f), -1};
  bones_[kSpine] = {"spine", glm::mat4(1.f), glm::mat4(1.f), kRoot};
  bones_[kHead] = {"head", glm::mat4(1.f), glm::mat4(1.f), kSpine};
  bones_[kLeftArm] = {"leftArm", glm::mat4(1.f), glm::mat4(1.f), kSpine};
  bones_[kRightArm] = {"rightArm", glm::mat4(1.f), glm::mat4(1.f), kSpine};
  bones_[kLeftLeg] = {"leftLeg", glm::mat4(1.f), glm::mat4(1.f), kRoot};
  bones_[kRightLeg] = {"rightLeg", glm::mat4(1.f), glm::mat4(1.f), kRoot};

  bindLocal_.fill(glm::mat4(1.f));
  bindLocal_[kSpine] = glm::translate(glm::mat4(1.f), glm::vec3(0.f, 0.16f, 0.f));
  bindLocal_[kHead] = glm::translate(glm::mat4(1.f), glm::vec3(0.f, 0.52f, 0.f));
  bindLocal_[kLeftArm] = glm::translate(glm::mat4(1.f), glm::vec3(0.22f, 0.46f, 0.f));
  bindLocal_[kRightArm] = glm::translate(glm::mat4(1.f), glm::vec3(-0.22f, 0.46f, 0.f));
  bindLocal_[kLeftLeg] = glm::translate(glm::mat4(1.f), glm::vec3(0.11f, -0.06f, 0.f));
  bindLocal_[kRightLeg] = glm::translate(glm::mat4(1.f), glm::vec3(-0.11f, -0.06f, 0.f));

  setPosePreset(AvatarPosePreset::TPose);
}

void Avatar::setRigMeshes(const std::array<Mesh*, kAvatarBodyPartCount>& parts) {
  bodyMeshes_ = parts;
  useRigMeshes_ = true;
  legacyBodyMesh_ = nullptr;
}

void Avatar::setBodyMesh(Mesh* mesh) {
  legacyBodyMesh_ = mesh;
  useRigMeshes_ = false;
  bodyMeshes_.fill(nullptr);
}

void Avatar::setPosePreset(AvatarPosePreset preset) {
  currentPose_ = preset;
  applyPosePresetLocals_(preset);
}

void Avatar::applyPosePresetLocals_(AvatarPosePreset p) {
  using glm::mat4;
  using glm::vec3;
  const mat4 I(1.f);
  poseLocal_.fill(I);

  const float deg = glm::radians(1.f);

  switch (p) {
  case AvatarPosePreset::TPose:
    // Horizontal arms; meshes already extend along ±X.
    poseLocal_[kLeftArm] = glm::rotate(I, 8.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kRightArm] = glm::rotate(I, -8.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kLeftLeg] = glm::rotate(I, 4.f * deg, vec3(1.f, 0.f, 0.f));
    poseLocal_[kRightLeg] = glm::rotate(I, 4.f * deg, vec3(1.f, 0.f, 0.f));
    break;

  case AvatarPosePreset::APose:
    poseLocal_[kLeftArm] = glm::rotate(I, -38.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kRightArm] = glm::rotate(I, 38.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kLeftLeg] = glm::rotate(I, 3.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kRightLeg] = glm::rotate(I, -3.f * deg, vec3(0.f, 0.f, 1.f));
    break;

  case AvatarPosePreset::Relaxed:
    poseLocal_[kSpine] = glm::rotate(I, -4.f * deg, vec3(1.f, 0.f, 0.f));
    poseLocal_[kHead] = glm::rotate(I, 6.f * deg, vec3(1.f, 0.f, 0.f));
    poseLocal_[kLeftArm] = glm::rotate(I, -72.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kRightArm] = glm::rotate(I, 72.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kLeftLeg] = glm::rotate(I, -6.f * deg, vec3(0.f, 0.f, 1.f));
    poseLocal_[kRightLeg] = glm::rotate(I, 8.f * deg, vec3(0.f, 0.f, 1.f));
    break;

  case AvatarPosePreset::WalkLike:
    poseLocal_[kSpine] = glm::rotate(I, 7.f * deg, vec3(0.f, 1.f, 0.f));
    poseLocal_[kHead] = glm::rotate(I, -5.f * deg, vec3(0.f, 1.f, 0.f));
    poseLocal_[kLeftLeg] = glm::rotate(I, -26.f * deg, vec3(1.f, 0.f, 0.f));
    poseLocal_[kRightLeg] = glm::rotate(I, 18.f * deg, vec3(1.f, 0.f, 0.f));
    poseLocal_[kLeftArm] = glm::rotate(I, -15.f * deg, vec3(1.f, 0.f, 0.f));
    poseLocal_[kRightArm] = glm::rotate(I, 22.f * deg, vec3(1.f, 0.f, 0.f));
    break;
  }
}

void Avatar::setTPose() { setPosePreset(AvatarPosePreset::TPose); }

void Avatar::update() {
  const glm::mat4 root = transform_.toMat4();
  for (std::size_t i = 0; i < bones_.size(); ++i) {
    Bone& b = bones_[i];
    const glm::mat4 local = bindLocal_[i] * poseLocal_[i];
    if (b.parentIndex < 0) {
      b.worldTransform = root * local;
    } else {
      b.worldTransform =
          bones_[static_cast<std::size_t>(b.parentIndex)].worldTransform * local;
    }
  }
}

ClothingLayer Avatar::makeClothingDefaults_(Mesh* mesh, ClothingTag tag,
                                            float uniformScale) {
  ClothingLayer L{};
  L.mesh = mesh;
  L.tag = tag;
  const float u = uniformScale > 0.f ? uniformScale : 1.f;
  const glm::mat4 Us = glm::scale(glm::mat4(1.f), glm::vec3(u));

  switch (tag) {
  case ClothingTag::Shirt:
    L.anchorBoneIndex = kSpine;
    L.localFromAnchor =
        glm::translate(glm::mat4(1.f), glm::vec3(0.f, 0.02f, 0.02f)) *
        glm::scale(glm::mat4(1.f), glm::vec3(1.06f, 1.05f, 1.08f)) * Us;
    L.tintRgb = glm::vec3(0.42f, 0.52f, 0.82f);
    break;
  case ClothingTag::Trousers:
    L.anchorBoneIndex = kRoot;
    L.localFromAnchor =
        glm::translate(glm::mat4(1.f), glm::vec3(0.f, 0.f, 0.f)) *
        glm::scale(glm::mat4(1.f), glm::vec3(1.04f, 1.03f, 1.05f)) * Us;
    L.tintRgb = glm::vec3(0.34f, 0.38f, 0.48f);
    break;
  case ClothingTag::Shoes:
    L.anchorBoneIndex = kRoot;
    L.localFromAnchor = glm::translate(glm::mat4(1.f), glm::vec3(0.f, 0.f, 0.f)) * Us;
    L.tintRgb = glm::vec3(0.20f, 0.17f, 0.15f);
    break;
  default:
    L.anchorBoneIndex = kRoot;
    L.localFromAnchor = Us;
    L.tintRgb = glm::vec3(0.55f, 0.55f, 0.58f);
    break;
  }
  return L;
}

void Avatar::addClothing(Mesh* mesh, ClothingTag tag, float uniformScale) {
  if (mesh == nullptr) return;
  clothing_.push_back(makeClothingDefaults_(mesh, tag, uniformScale));
}

bool Avatar::removeClothing(const Mesh* mesh) {
  const auto it = std::remove_if(
      clothing_.begin(), clothing_.end(),
      [mesh](const ClothingLayer& L) { return L.mesh == mesh; });
  if (it == clothing_.end()) return false;
  clothing_.erase(it, clothing_.end());
  return true;
}

void Avatar::clearClothing() { clothing_.clear(); }

void Avatar::renderBodyParts_(Renderer& renderer, const glm::mat4& view,
                              const glm::mat4& projection) {
  const glm::vec3 skin(0.84f, 0.79f, 0.73f);
  for (int i = 0; i < kAvatarBodyPartCount; ++i) {
    if (bodyMeshes_[static_cast<std::size_t>(i)] == nullptr) continue;
    renderer.setMeshColor(skin);
    renderer.renderMesh(*bodyMeshes_[static_cast<std::size_t>(i)], bones_[static_cast<std::size_t>(i)].worldTransform,
                        view, projection);
  }
}

void Avatar::renderClothingLayers_(Renderer& renderer, const glm::mat4& view,
                                   const glm::mat4& projection) {
  for (const ClothingLayer& layer : clothing_) {
    if (layer.mesh == nullptr) continue;
    const int ai = clampBoneIndex(layer.anchorBoneIndex);
    const glm::mat4 model = bones_[static_cast<std::size_t>(ai)].worldTransform * layer.localFromAnchor;
    renderer.setMeshColor(layer.tintRgb);
    renderer.renderMesh(*layer.mesh, model, view, projection);
  }
}

void Avatar::render(Renderer& renderer, const glm::mat4& view,
                    const glm::mat4& projection) {
  const glm::mat4 root = transform_.toMat4();

  if (useRigMeshes_) {
    renderBodyParts_(renderer, view, projection);
  } else if (legacyBodyMesh_ != nullptr) {
    renderer.setMeshColor(glm::vec3(0.84f, 0.79f, 0.73f));
    renderer.renderMesh(*legacyBodyMesh_, root, view, projection);
  }

  renderClothingLayers_(renderer, view, projection);

  if (showSkeletonDebug_) {
    const glm::vec4 lineRgb(0.15f, 0.95f, 0.35f, 1.f);
    for (std::size_t i = 0; i < bones_.size(); ++i) {
      const Bone& b = bones_[i];
      if (b.parentIndex < 0) continue;
      const Bone& p = bones_[static_cast<std::size_t>(b.parentIndex)];
      renderer.drawLine(worldPos(p.worldTransform), worldPos(b.worldTransform), view,
                        projection, lineRgb);
    }
  }
}

} // namespace closy
