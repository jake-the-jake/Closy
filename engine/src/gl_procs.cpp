#include "gl_procs.hpp"

#include <cstdio>

namespace {

using LoadFn = void* (*)(const char*);

void* getp(LoadFn load, const char* name) {
  if (load == nullptr) return nullptr;
  void* p = load(name);
  if (p != nullptr) return p;
  char buf[176];
  std::snprintf(buf, sizeof(buf), "%sARB", name);
  p = load(buf);
  if (p != nullptr) return p;
  std::snprintf(buf, sizeof(buf), "%sEXT", name);
  return load(buf);
}

#define ASSIGN(field, Name, Type)                                                     \
  do {                                                                                \
    g.field = reinterpret_cast<Type>(getp(load, #Name));                             \
    if (g.field == nullptr) {                                                        \
      std::fprintf(stderr, "[closy] Missing GL: %s\n", #Name);                       \
      return false;                                                                   \
    }                                                                                 \
  } while (0)

} // namespace

bool closyLoadGlProcs(GlProcs& g, void* (*getProc)(const char*)) {
  auto load = reinterpret_cast<LoadFn>(getProc);

  ASSIGN(clearColor, glClearColor, decltype(g.clearColor));
  ASSIGN(clear, glClear, decltype(g.clear));
  ASSIGN(viewport, glViewport, decltype(g.viewport));
  ASSIGN(enable, glEnable, decltype(g.enable));
  ASSIGN(depthFunc, glDepthFunc, decltype(g.depthFunc));

  g.polygonMode = reinterpret_cast<decltype(g.polygonMode)>(getp(load, "glPolygonMode"));
  g.lineWidth = reinterpret_cast<decltype(g.lineWidth)>(getp(load, "glLineWidth"));

  ASSIGN(genVertexArrays, glGenVertexArrays, decltype(g.genVertexArrays));
  ASSIGN(bindVertexArray, glBindVertexArray, decltype(g.bindVertexArray));
  ASSIGN(genBuffers, glGenBuffers, decltype(g.genBuffers));
  ASSIGN(bindBuffer, glBindBuffer, decltype(g.bindBuffer));
  ASSIGN(bufferData, glBufferData, decltype(g.bufferData));
  ASSIGN(vertexAttribPointer, glVertexAttribPointer, decltype(g.vertexAttribPointer));
  ASSIGN(enableVertexAttribArray, glEnableVertexAttribArray,
       decltype(g.enableVertexAttribArray));
  ASSIGN(drawElements, glDrawElements, decltype(g.drawElements));
  ASSIGN(drawArrays, glDrawArrays, decltype(g.drawArrays));

  ASSIGN(createShader, glCreateShader, decltype(g.createShader));
  ASSIGN(shaderSource, glShaderSource, decltype(g.shaderSource));
  ASSIGN(compileShader, glCompileShader, decltype(g.compileShader));
  ASSIGN(getShaderiv, glGetShaderiv, decltype(g.getShaderiv));
  ASSIGN(getShaderInfoLog, glGetShaderInfoLog, decltype(g.getShaderInfoLog));
  ASSIGN(createProgram, glCreateProgram, decltype(g.createProgram));
  ASSIGN(attachShader, glAttachShader, decltype(g.attachShader));
  ASSIGN(linkProgram, glLinkProgram, decltype(g.linkProgram));
  ASSIGN(getProgramiv, glGetProgramiv, decltype(g.getProgramiv));
  ASSIGN(getProgramInfoLog, glGetProgramInfoLog, decltype(g.getProgramInfoLog));
  ASSIGN(useProgram, glUseProgram, decltype(g.useProgram));
  ASSIGN(deleteShader, glDeleteShader, decltype(g.deleteShader));
  ASSIGN(deleteProgram, glDeleteProgram, decltype(g.deleteProgram));
  ASSIGN(getUniformLocation, glGetUniformLocation, decltype(g.getUniformLocation));
  ASSIGN(uniformMatrix4fv, glUniformMatrix4fv, decltype(g.uniformMatrix4fv));
  ASSIGN(uniform3fv, glUniform3fv, decltype(g.uniform3fv));
  ASSIGN(uniform4fv, glUniform4fv, decltype(g.uniform4fv));
  ASSIGN(deleteVertexArrays, glDeleteVertexArrays, decltype(g.deleteVertexArrays));
  ASSIGN(deleteBuffers, glDeleteBuffers, decltype(g.deleteBuffers));

#undef ASSIGN

  if (g.polygonMode == nullptr) {
    g.polygonMode = +[](unsigned int, unsigned int) {};
  }
  if (g.lineWidth == nullptr) {
    g.lineWidth = +[](float) {};
  }

  return true;
}
