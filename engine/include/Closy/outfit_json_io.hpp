#pragma once

#include <Closy/outfit_description.hpp>

#include <string>

namespace closy {

bool parseOutfitJsonFile(const char* path, OutfitDescription& out, std::string& err);

} // namespace closy
