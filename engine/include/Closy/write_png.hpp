#pragma once

#include <cstddef>

namespace closy {

/** RGBA8, row-major top-first. Returns true on success. */
bool writePngRgba8(const char* path, int width, int height, const unsigned char* rgbaTopFirst);

} // namespace closy
