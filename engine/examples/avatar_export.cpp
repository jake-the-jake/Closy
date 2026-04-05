/**
 * CLI: render avatar to PNG (hidden GLFW window + FBO).
 * Example: avatar_export --out preview.png --pose relaxed --width 1024 --height 1024
 *          avatar_export --out look.png --outfit example_outfits/outfit_navy.json
 */
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#include <Closy/Avatar.hpp>
#include <Closy/AvatarPose.hpp>
#include <Closy/AvatarPreviewExport.hpp>
#include <Closy/GlRenderer.hpp>
#include <Closy/OffscreenCapture.hpp>
#include <Closy/Scene.hpp>
#include <Closy/gl_procs.hpp>
#include <Closy/outfit_builder.hpp>
#include <Closy/outfit_description.hpp>
#include <Closy/outfit_json_io.hpp>
#include <Closy/write_png.hpp>

#include <glm/gtc/matrix_transform.hpp>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {

void glfwError(int code, const char* desc) { std::fprintf(stderr, "GLFW %i: %s\n", code, desc); }

bool streq(const char* a, const char* b) { return a && b && std::strcmp(a, b) == 0; }

const char* poseSlug(closy::AvatarPosePreset p) {
  switch (p) {
  case closy::AvatarPosePreset::TPose:
    return "tpose";
  case closy::AvatarPosePreset::APose:
    return "apose";
  case closy::AvatarPosePreset::Relaxed:
    return "relaxed";
  case closy::AvatarPosePreset::WalkLike:
    return "walk";
  }
  return "unknown";
}

bool parsePose(const char* s, closy::AvatarPosePreset& out) {
  if (!s) return false;
  if (streq(s, "tpose") || streq(s, "Tpose") || streq(s, "TPose")) {
    out = closy::AvatarPosePreset::TPose;
    return true;
  }
  if (streq(s, "apose") || streq(s, "A-pose") || streq(s, "Apose")) {
    out = closy::AvatarPosePreset::APose;
    return true;
  }
  if (streq(s, "relaxed")) {
    out = closy::AvatarPosePreset::Relaxed;
    return true;
  }
  if (streq(s, "walk")) {
    out = closy::AvatarPosePreset::WalkLike;
    return true;
  }
  return false;
}

bool parsePoseStringLoose(const std::string& str, closy::AvatarPosePreset& out) {
  return parsePose(str.c_str(), out);
}

bool parseCameraCli(const char* s, closy::AvatarExportCameraPreset& out) {
  if (!s) return false;
  return closy::avatarExportCameraFromJsonString(std::string(s), out);
}

void printUsage() {
  std::fprintf(stderr,
               "Usage: avatar_export --out <file.png> [options]\n"
               "  --pose tpose|apose|relaxed|walk\n"
               "  --width N  --height N\n"
               "  --all-poses\n"
               "  --outfit <path.json>\n"
               "  --camera three_quarter|front|side  (overrides outfit JSON camera)\n");
}

struct Options {
  const char* outPath = nullptr;
  const char* outfitPath = nullptr;
  closy::AvatarPosePreset pose = closy::AvatarPosePreset::Relaxed;
  bool poseFromCli = false;
  int width = 1024;
  int height = 1024;
  bool widthFromCli = false;
  bool heightFromCli = false;
  closy::AvatarExportCameraPreset camera = closy::AvatarExportCameraPreset::ThreeQuarter;
  bool cameraFromCli = false;
  bool allPoses = false;
};

bool parseArgs(int argc, char** argv, Options& opt) {
  for (int i = 1; i < argc; ++i) {
    if (streq(argv[i], "--out") && i + 1 < argc) {
      opt.outPath = argv[++i];
    } else if (streq(argv[i], "--outfit") && i + 1 < argc) {
      opt.outfitPath = argv[++i];
    } else if (streq(argv[i], "--pose") && i + 1 < argc) {
      if (!parsePose(argv[++i], opt.pose)) {
        std::fprintf(stderr, "Unknown pose\n");
        return false;
      }
      opt.poseFromCli = true;
    } else if (streq(argv[i], "--width") && i + 1 < argc) {
      opt.width = std::atoi(argv[++i]);
      opt.widthFromCli = true;
    } else if (streq(argv[i], "--height") && i + 1 < argc) {
      opt.height = std::atoi(argv[++i]);
      opt.heightFromCli = true;
    } else if (streq(argv[i], "--camera") && i + 1 < argc) {
      if (!parseCameraCli(argv[++i], opt.camera)) {
        std::fprintf(stderr, "Unknown camera preset\n");
        return false;
      }
      opt.cameraFromCli = true;
    } else if (streq(argv[i], "--all-poses")) {
      opt.allPoses = true;
    } else if (streq(argv[i], "-h") || streq(argv[i], "--help")) {
      return false;
    } else {
      std::fprintf(stderr, "Unknown arg: %s\n", argv[i]);
      return false;
    }
  }
  if (opt.outPath == nullptr) {
    std::fprintf(stderr, "Missing --out\n");
    return false;
  }
  if (opt.width <= 0 || opt.height <= 0) {
    std::fprintf(stderr, "Invalid size\n");
    return false;
  }
  return true;
}

bool exportOnePose(GlProcs& glp, closy::GlRenderer& renderer, closy::Scene& scene,
                   closy::Avatar* avatar, const char* pngPath, int width, int height,
                   closy::AvatarPosePreset pose, float yaw, float pitch,
                   const glm::vec4& clearColor) {
  avatar->setPosePreset(pose);
  scene.update();

  const glm::vec3 focus = avatar->focusPointWorld();
  const float aspect = static_cast<float>(width) / static_cast<float>(height);
  const glm::mat4 view =
      closy::avatarExportView(focus, yaw, pitch, closy::kAvatarExportDistance);
  const glm::mat4 proj = closy::avatarExportProjection(aspect, closy::kAvatarExportFovDeg);

  std::vector<unsigned char> rgba;
  const bool ok = closy::captureFrameToRgba(
      glp, renderer, width, height, clearColor,
      [&](closy::Renderer& r) { scene.render(r, view, proj); }, rgba);

  if (!ok || rgba.empty()) {
    std::fprintf(stderr, "[closy] Export render failed: %s\n", pngPath);
    return false;
  }
  if (!closy::writePngRgba8(pngPath, width, height, rgba.data())) {
    std::fprintf(stderr, "[closy] PNG write failed: %s\n", pngPath);
    return false;
  }
  std::printf("[closy] Exported: %s\n", pngPath);
  std::printf("[closy] Pose: %s\n", closy::avatarPosePresetLabel(pose));
  std::printf("[closy] Size: %ix%i\n", width, height);
  return true;
}

} // namespace

int main(int argc, char** argv) {
  Options opt{};
  if (!parseArgs(argc, argv, opt)) {
    printUsage();
    return 1;
  }

  closy::OutfitDescription outfitDesc = closy::defaultDemoOutfitDescription();
  if (opt.outfitPath != nullptr) {
    std::string err;
    if (!closy::parseOutfitJsonFile(opt.outfitPath, outfitDesc, err)) {
      std::fprintf(stderr, "[closy] Outfit JSON: %s\n", err.c_str());
      return 1;
    }
  }

  int width = outfitDesc.width;
  int height = outfitDesc.height;
  if (opt.widthFromCli) width = opt.width;
  if (opt.heightFromCli) height = opt.height;

  closy::AvatarPosePreset pose = closy::AvatarPosePreset::Relaxed;
  if (opt.poseFromCli) {
    pose = opt.pose;
  } else if (!parsePoseStringLoose(outfitDesc.pose, pose)) {
    std::fprintf(stderr, "[closy] Unknown pose in outfit file: %s\n", outfitDesc.pose.c_str());
    return 1;
  }

  closy::AvatarExportCameraPreset cam = closy::AvatarExportCameraPreset::ThreeQuarter;
  if (opt.cameraFromCli) {
    cam = opt.camera;
  } else if (!closy::avatarExportCameraFromJsonString(outfitDesc.camera, cam)) {
    std::fprintf(stderr, "[closy] Unknown camera in outfit file: %s (using three_quarter)\n",
                 outfitDesc.camera.c_str());
    cam = closy::AvatarExportCameraPreset::ThreeQuarter;
  }

  float yaw = 0.f, pitch = 0.f;
  closy::exportCameraAngles(cam, yaw, pitch);

  glfwSetErrorCallback(glfwError);
  if (!glfwInit())
    return 1;

  glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
  glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
  glfwWindowHint(GLFW_VISIBLE, GLFW_FALSE);
#ifdef __APPLE__
  glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GLFW_TRUE);
#endif

  GLFWwindow* window = glfwCreateWindow(16, 16, "closy export", nullptr, nullptr);
  if (window == nullptr) {
    glfwTerminate();
    return 1;
  }
  glfwMakeContextCurrent(window);

  GlProcs glp{};
  if (!closyLoadGlProcs(glp, reinterpret_cast<void* (*)(const char*)>(glfwGetProcAddress))) {
    glfwDestroyWindow(window);
    glfwTerminate();
    return 1;
  }

  closy::GlRenderer renderer(glp);
  closy::Scene scene;
  closy::Avatar* avatar = scene.spawnAvatar();
  closy::buildOutfitFromDescription(scene, *avatar, outfitDesc);

  const glm::vec4 clearColor(0.08f, 0.09f, 0.11f, 1.f);
  bool allOk = true;

  if (opt.allPoses) {
    const closy::AvatarPosePreset presets[] = {
        closy::AvatarPosePreset::TPose,
        closy::AvatarPosePreset::APose,
        closy::AvatarPosePreset::Relaxed,
        closy::AvatarPosePreset::WalkLike,
    };
    char pathBuf[512];
    for (closy::AvatarPosePreset pr : presets) {
      char suffix[32];
      std::snprintf(suffix, sizeof(suffix), "_%s", poseSlug(pr));
      if (!closy::pngPathWithSuffix(opt.outPath, suffix, pathBuf, sizeof(pathBuf))) {
        std::fprintf(stderr, "[closy] Path too long\n");
        allOk = false;
        break;
      }
      if (!exportOnePose(glp, renderer, scene, avatar, pathBuf, width, height, pr, yaw, pitch,
                         clearColor))
        allOk = false;
    }
  } else {
    allOk = exportOnePose(glp, renderer, scene, avatar, opt.outPath, width, height, pose, yaw,
                          pitch, clearColor);
  }

  glfwDestroyWindow(window);
  glfwTerminate();
  return allOk ? 0 : 1;
}
