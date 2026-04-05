#pragma once

#include <cstddef>

/** Loaded via GLFW / glfwGetProcAddress (OpenGL 3.3 Core subset + FBO + PNG readback). */
struct GlProcs {
  void (*clearColor)(float, float, float, float) = nullptr;
  void (*clear)(unsigned int) = nullptr;
  void (*viewport)(int, int, int, int) = nullptr;
  void (*enable)(unsigned int) = nullptr;
  void (*disable)(unsigned int) = nullptr;
  void (*depthFunc)(unsigned int) = nullptr;
  void (*polygonMode)(unsigned int, unsigned int) = nullptr;
  void (*lineWidth)(float) = nullptr;
  void (*pixelStorei)(unsigned int, int) = nullptr;

  void (*genVertexArrays)(int, unsigned int*) = nullptr;
  void (*bindVertexArray)(unsigned int) = nullptr;
  void (*genBuffers)(int, unsigned int*) = nullptr;
  void (*bindBuffer)(unsigned int, unsigned int) = nullptr;
  void (*bufferData)(unsigned int, std::ptrdiff_t, const void*, unsigned int) = nullptr;
  void (*vertexAttribPointer)(unsigned int, int, unsigned int, unsigned char, int,
                              const void*) = nullptr;
  void (*enableVertexAttribArray)(unsigned int) = nullptr;
  void (*drawElements)(unsigned int, int, unsigned int, const void*) = nullptr;
  void (*drawArrays)(unsigned int, int, int) = nullptr;

  unsigned int (*createShader)(unsigned int) = nullptr;
  void (*shaderSource)(unsigned int, int, const char* const*, const int*) = nullptr;
  void (*compileShader)(unsigned int) = nullptr;
  void (*getShaderiv)(unsigned int, unsigned int, int*) = nullptr;
  void (*getShaderInfoLog)(unsigned int, int, int*, char*) = nullptr;
  unsigned int (*createProgram)() = nullptr;
  void (*attachShader)(unsigned int, unsigned int) = nullptr;
  void (*linkProgram)(unsigned int) = nullptr;
  void (*getProgramiv)(unsigned int, unsigned int, int*) = nullptr;
  void (*getProgramInfoLog)(unsigned int, int, int*, char*) = nullptr;
  void (*useProgram)(unsigned int) = nullptr;
  void (*deleteShader)(unsigned int) = nullptr;
  void (*deleteProgram)(unsigned int) = nullptr;
  int (*getUniformLocation)(unsigned int, const char*) = nullptr;
  void (*uniformMatrix4fv)(int, int, unsigned char, const float*) = nullptr;
  void (*uniform3fv)(int, int, const float*) = nullptr;
  void (*uniform4fv)(int, int, const float*) = nullptr;
  void (*deleteVertexArrays)(int, unsigned int*) = nullptr;
  void (*deleteBuffers)(int, unsigned int*) = nullptr;

  void (*genFramebuffers)(int, unsigned int*) = nullptr;
  void (*bindFramebuffer)(unsigned int, unsigned int) = nullptr;
  void (*deleteFramebuffers)(int, unsigned int*) = nullptr;
  unsigned int (*checkFramebufferStatus)(unsigned int) = nullptr;
  void (*framebufferTexture2D)(unsigned int, unsigned int, unsigned int, unsigned int, int) =
      nullptr;
  void (*framebufferRenderbuffer)(unsigned int, unsigned int, unsigned int, unsigned int) =
      nullptr;
  void (*genRenderbuffers)(int, unsigned int*) = nullptr;
  void (*bindRenderbuffer)(unsigned int, unsigned int) = nullptr;
  void (*renderbufferStorage)(unsigned int, unsigned int, int, int) = nullptr;
  void (*deleteRenderbuffers)(int, unsigned int*) = nullptr;
  void (*genTextures)(int, unsigned int*) = nullptr;
  void (*bindTexture)(unsigned int, unsigned int) = nullptr;
  void (*texImage2D)(unsigned int, int, int, int, int, int, unsigned int, unsigned int,
                     const void*) = nullptr;
  void (*texParameteri)(unsigned int, unsigned int, int) = nullptr;
  void (*deleteTextures)(int, unsigned int*) = nullptr;
  void (*readPixels)(int, int, int, int, unsigned int, unsigned int, void*) = nullptr;
};

bool closyLoadGlProcs(GlProcs& g, void* (*getProc)(const char*));
