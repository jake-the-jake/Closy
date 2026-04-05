#pragma once

#include <array>
#include <cstdint>
#include <memory>
#include <vector>

namespace closy {

constexpr std::size_t kMannequinPartCount = 7;

/**
 * CPU-side mesh + optional GPU handles (owned by Renderer after first upload).
 * Interleaved: 6 floats per vertex — position (vec3), normal (vec3).
 */
class Mesh {
public:
  std::vector<float> interleavedVertices;
  std::vector<std::uint32_t> indices;

  Mesh() = default;
  virtual ~Mesh() = default;

  static std::unique_ptr<Mesh> createUnitCube();

  /**
   * Procedural mannequin as seven rigid parts (pelvis, torso, head, arms, legs),
   * each authored in **local bone space** (same order as `AvatarBodyPart` / `AvatarBoneId`).
   */
  using MannequinRigArray = std::array<std::unique_ptr<Mesh>, kMannequinPartCount>;
  static MannequinRigArray createMannequinRig();

  /** Legacy fused mannequin (single draw); kept for compatibility. */
  static std::unique_ptr<Mesh> createMannequin();

  /** Torso / jumper shell only — anchor to spine (sleeves use `createShirtSleeveProxy` on arms). */
  static std::unique_ptr<Mesh> createShirtTorsoProxy();
  /** One sleeve — anchor to LeftArm or RightArm; geometry matches +X arm axis (mirror for right). */
  static std::unique_ptr<Mesh> createShirtSleeveProxy();
  /** Waist/hip band only — anchor to pelvis/root bone. */
  static std::unique_ptr<Mesh> createTrousersHipProxy();
  /** One leg sleeve — anchor to LeftLeg or RightLeg bone; geometry in leg-local axes. */
  static std::unique_ptr<Mesh> createTrousersLegProxy();
  static std::unique_ptr<Mesh> createTrousersProxy();
  static std::unique_ptr<Mesh> createShoesProxy();
};

} // namespace closy
