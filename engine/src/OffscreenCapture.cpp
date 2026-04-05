#include <Closy/OffscreenCapture.hpp>
#include <Closy/GlRenderer.hpp>

#include <cstdio>
#include <cstring>

namespace closy {
namespace {

constexpr unsigned kGL_FRAMEBUFFER = 0x8D40;
constexpr unsigned kGL_COLOR_ATTACHMENT0 = 0x8CE0;
constexpr unsigned kGL_FRAMEBUFFER_COMPLETE = 0x8CD5;
constexpr unsigned kGL_DEPTH_ATTACHMENT = 0x8D00;
constexpr unsigned kGL_DEPTH_COMPONENT24 = 0x81A6;
constexpr unsigned kGL_RENDERBUFFER = 0x8D41;
constexpr unsigned kGL_TEXTURE_2D = 0x0DE1;
constexpr unsigned kGL_RGBA = 0x1908;
constexpr unsigned kGL_UNSIGNED_BYTE = 0x1401;
constexpr unsigned kGL_NEAREST = 0x2600;
constexpr unsigned kGL_CLAMP_TO_EDGE = 0x812F;
constexpr unsigned kGL_PACK_ALIGNMENT = 0x0D05;
constexpr unsigned kGL_RGB8 = 0x8051;
constexpr unsigned kGL_RGBA8 = 0x8058;

} // namespace

void flipRgbaRowsInPlace(int width, int height, std::vector<std::uint8_t>& rgba) {
  const std::size_t row = static_cast<std::size_t>(width) * 4u;
  std::vector<std::uint8_t> tmp(row);
  for (int y = 0; y < height / 2; ++y) {
    std::uint8_t* top = rgba.data() + static_cast<std::size_t>(y) * row;
    std::uint8_t* bot = rgba.data() + static_cast<std::size_t>(height - 1 - y) * row;
    std::memcpy(tmp.data(), top, row);
    std::memcpy(top, bot, row);
    std::memcpy(bot, tmp.data(), row);
  }
}

bool captureFrameToRgba(GlProcs& gl, GlRenderer& renderer, int width, int height,
                        const glm::vec4& clearColor,
                        const std::function<void(Renderer&)>& draw,
                        std::vector<std::uint8_t>& outRgba) {
  if (width <= 0 || height <= 0) return false;

  unsigned fbo = 0;
  unsigned colorTex = 0;
  unsigned depthRbo = 0;
  gl.genFramebuffers(1, &fbo);
  gl.genTextures(1, &colorTex);
  gl.genRenderbuffers(1, &depthRbo);

  gl.bindTexture(kGL_TEXTURE_2D, colorTex);
  gl.texImage2D(kGL_TEXTURE_2D, 0, static_cast<int>(kGL_RGBA8), width, height, 0, kGL_RGBA,
                kGL_UNSIGNED_BYTE, nullptr);
  gl.texParameteri(kGL_TEXTURE_2D, 0x2801, static_cast<int>(kGL_NEAREST)); // GL_TEXTURE_MIN_FILTER
  gl.texParameteri(kGL_TEXTURE_2D, 0x2800, static_cast<int>(kGL_NEAREST)); // GL_TEXTURE_MAG_FILTER
  gl.texParameteri(kGL_TEXTURE_2D, 0x2802, static_cast<int>(kGL_CLAMP_TO_EDGE)); // S
  gl.texParameteri(kGL_TEXTURE_2D, 0x2803, static_cast<int>(kGL_CLAMP_TO_EDGE)); // T

  gl.bindRenderbuffer(kGL_RENDERBUFFER, depthRbo);
  gl.renderbufferStorage(kGL_RENDERBUFFER, kGL_DEPTH_COMPONENT24, width, height);

  gl.bindFramebuffer(kGL_FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(kGL_FRAMEBUFFER, kGL_COLOR_ATTACHMENT0, kGL_TEXTURE_2D, colorTex, 0);
  gl.framebufferRenderbuffer(kGL_FRAMEBUFFER, kGL_DEPTH_ATTACHMENT, kGL_RENDERBUFFER, depthRbo);

  if (gl.checkFramebufferStatus(kGL_FRAMEBUFFER) != kGL_FRAMEBUFFER_COMPLETE) {
    std::fprintf(stderr, "[closy] FBO incomplete\n");
    gl.bindFramebuffer(kGL_FRAMEBUFFER, 0);
    gl.deleteRenderbuffers(1, &depthRbo);
    gl.deleteTextures(1, &colorTex);
    gl.deleteFramebuffers(1, &fbo);
    return false;
  }

  gl.viewport(0, 0, width, height);
  renderer.beginFrame(clearColor);
  draw(renderer);
  renderer.endFrame();

  gl.pixelStorei(kGL_PACK_ALIGNMENT, 1);
  outRgba.resize(static_cast<std::size_t>(width * height) * 4u);
  gl.readPixels(0, 0, width, height, kGL_RGBA, kGL_UNSIGNED_BYTE, outRgba.data());

  gl.bindFramebuffer(kGL_FRAMEBUFFER, 0);
  gl.deleteRenderbuffers(1, &depthRbo);
  gl.deleteTextures(1, &colorTex);
  gl.deleteFramebuffers(1, &fbo);

  flipRgbaRowsInPlace(width, height, outRgba);
  return true;
}

} // namespace closy
