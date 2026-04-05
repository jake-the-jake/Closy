#include <Closy/write_png.hpp>

#define STB_IMAGE_WRITE_IMPLEMENTATION
#include "stb_image_write.h"

namespace closy {

bool writePngRgba8(const char* path, int width, int height, const unsigned char* rgbaTopFirst) {
  if (path == nullptr || rgbaTopFirst == nullptr || width <= 0 || height <= 0) return false;
  const int ok =
      stbi_write_png(path, width, height, 4, rgbaTopFirst, width * 4);
  return ok != 0;
}

} // namespace closy
