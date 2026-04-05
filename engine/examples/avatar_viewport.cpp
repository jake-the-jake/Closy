/**
 * Avatar demo: orbit (LMB drag), poses 1–4, B skeleton, R camera, Esc quit.
 */
#define GLFW_INCLUDE_NONE
#include <GLFW/glfw3.h>

#include <Closy/Avatar.hpp>
#include <Closy/AvatarPose.hpp>
#include <Closy/GlRenderer.hpp>
#include <Closy/Mesh.hpp>
#include <Closy/Scene.hpp>
#include <Closy/avatar_demo_outfit.hpp>
#include <Closy/gl_procs.hpp>

#include <glm/gtc/matrix_transform.hpp>

#include <algorithm>
#include <cstdio>
#include <cmath>

namespace {

struct OrbitCam {
  static constexpr float kYaw0 = 0.52f;
  static constexpr float kPitch0 = 0.13f;
  /** Far enough to frame ~2m character + leg swing in 45° FOV. */
  static constexpr float kDist0 = 5.75f;
  float yaw = kYaw0;
  float pitch = kPitch0;
  float dist = kDist0;
  glm::vec3 target{0.f, 0.48f, 0.f};

  glm::mat4 view() const {
    const float x = std::cos(yaw) * std::cos(pitch) * dist;
    const float y = std::sin(pitch) * dist;
    const float z = std::sin(yaw) * std::cos(pitch) * dist;
    const glm::vec3 eye = target + glm::vec3(x, y, z);
    return glm::lookAt(eye, target, glm::vec3(0.f, 1.f, 0.f));
  }

  void reset() {
    yaw = kYaw0;
    pitch = kPitch0;
    dist = kDist0;
  }
};

struct AppState {
  OrbitCam cam;
  closy::Avatar* avatar = nullptr;
  GLFWwindow* window = nullptr;
  bool showSkel = false;
  bool dragging = false;
  double lastX = 0;
  double lastY = 0;
};

void glfwError(int code, const char* desc) {
  std::fprintf(stderr, "GLFW %i: %s\n", code, desc);
}

void onCursor(GLFWwindow* w, double x, double y) {
  auto* app = static_cast<AppState*>(glfwGetWindowUserPointer(w));
  const int left = glfwGetMouseButton(w, GLFW_MOUSE_BUTTON_LEFT);
  if (left == GLFW_PRESS) {
    if (app->dragging) {
      app->cam.yaw += static_cast<float>(x - app->lastX) * 0.005f;
      app->cam.pitch += static_cast<float>(y - app->lastY) * 0.005f;
      app->cam.pitch = std::clamp(app->cam.pitch, -1.35f, 1.35f);
    }
    app->dragging = true;
  } else {
    app->dragging = false;
  }
  app->lastX = x;
  app->lastY = y;
}

void setPoseFromKey(AppState& app, closy::AvatarPosePreset p) {
  if (app.avatar == nullptr) return;
  app.avatar->setPosePreset(p);
  std::fprintf(stdout, "[closy] Pose: %s\n", closy::avatarPosePresetLabel(p));
  if (app.window != nullptr) {
    char title[160];
    std::snprintf(title, sizeof(title), "Closy Avatar — %s",
                  closy::avatarPosePresetLabel(p));
    glfwSetWindowTitle(app.window, title);
  }
}

} // namespace

int main() {
  glfwSetErrorCallback(glfwError);
  if (!glfwInit())
    return 1;

  glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 3);
  glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 3);
  glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
#ifdef __APPLE__
  glfwWindowHint(GLFW_OPENGL_FORWARD_COMPAT, GLFW_TRUE);
#endif

  GLFWwindow* window =
      glfwCreateWindow(960, 540, "Closy Avatar — T-Pose", nullptr, nullptr);
  if (window == nullptr) {
    glfwTerminate();
    return 1;
  }
  glfwMakeContextCurrent(window);
  glfwSwapInterval(1);

  GlProcs glp{};
  if (!closyLoadGlProcs(
          glp, reinterpret_cast<void* (*)(const char*)>(glfwGetProcAddress))) {
    glfwDestroyWindow(window);
    glfwTerminate();
    return 1;
  }

  closy::GlRenderer renderer(glp);
  closy::Scene scene;
  closy::Avatar* avatar = scene.spawnAvatar();

  closy::attachDemoOutfit(scene, avatar);

  AppState app{};
  app.avatar = avatar;
  app.window = window;
  app.showSkel = false;
  avatar->setShowSkeletonDebug(app.showSkel);
  glfwSetWindowUserPointer(window, &app);
  glfwSetCursorPosCallback(window, onCursor);

  std::fprintf(stdout,
               "[closy] Controls: 1–4 pose | B skeleton debug | R camera reset | LMB drag "
               "orbit | Esc quit\n");
  std::fprintf(stdout,
               "[closy] Skeleton overlay: depth off — bright yellow lines on top of mesh\n");

  while (!glfwWindowShouldClose(window)) {
    int fbW = 0, fbH = 0;
    glfwGetFramebufferSize(window, &fbW, &fbH);
    glp.viewport(0, 0, fbW, fbH);

    const float aspect =
        fbH > 0 ? static_cast<float>(fbW) / static_cast<float>(fbH) : 1.f;
    const glm::mat4 proj =
        glm::perspective(glm::radians(45.f), aspect, 0.1f, 100.f);

    renderer.beginFrame();
    scene.update();
    app.cam.target = app.avatar->focusPointWorld();
    scene.render(renderer, app.cam.view(), proj);
    renderer.endFrame();

    glfwSwapBuffers(window);
    glfwPollEvents();

    if (glfwGetKey(window, GLFW_KEY_ESCAPE) == GLFW_PRESS)
      glfwSetWindowShouldClose(window, GLFW_TRUE);

    auto keyEdge = [window](int key, int& was) {
      const int now = glfwGetKey(window, key);
      const bool edge = (now == GLFW_PRESS && was == GLFW_RELEASE);
      was = now;
      return edge;
    };

    static int bWas = GLFW_RELEASE;
    if (keyEdge(GLFW_KEY_B, bWas)) {
      app.showSkel = !app.showSkel;
      app.avatar->setShowSkeletonDebug(app.showSkel);
      std::fprintf(stdout, "[closy] Skeleton debug: %s\n",
                   app.showSkel ? "ON" : "OFF");
    }

    static int k1 = GLFW_RELEASE, k2 = GLFW_RELEASE, k3 = GLFW_RELEASE, k4 = GLFW_RELEASE;
    if (keyEdge(GLFW_KEY_1, k1))
      setPoseFromKey(app, closy::AvatarPosePreset::TPose);
    if (keyEdge(GLFW_KEY_2, k2))
      setPoseFromKey(app, closy::AvatarPosePreset::APose);
    if (keyEdge(GLFW_KEY_3, k3))
      setPoseFromKey(app, closy::AvatarPosePreset::Relaxed);
    if (keyEdge(GLFW_KEY_4, k4))
      setPoseFromKey(app, closy::AvatarPosePreset::WalkLike);

    static int rWas = GLFW_RELEASE;
    if (keyEdge(GLFW_KEY_R, rWas)) {
      app.cam.reset();
      std::fprintf(stdout, "[closy] Camera reset (orbit focus follows avatar torso)\n");
    }
  }

  glfwDestroyWindow(window);
  glfwTerminate();
  return 0;
}
