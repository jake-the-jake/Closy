#pragma once

#include <Closy/Renderer.hpp>
#include <Closy/gl_procs.hpp>

#include <glm/glm.hpp>

#include <cstdint>
#include <functional>
#include <vector>

namespace closy {

class GlRenderer;

/**
 * Renders into an RGBA8 FBO (no window swap). Clears with `clearColor`, then invokes `draw`.
 * `draw` should only issue draws (e.g. `scene.render`); do not call `beginFrame`/`swapBuffers`.
 */
bool captureFrameToRgba(GlProcs& gl, GlRenderer& renderer, int width, int height,
                        const glm::vec4& clearColor,
                        const std::function<void(Renderer&)>& draw, std::vector<std::uint8_t>& outRgba);

/** Flip GL bottom-origin rows to top-first for PNG. */
void flipRgbaRowsInPlace(int width, int height, std::vector<std::uint8_t>& rgba);

} // namespace closy
