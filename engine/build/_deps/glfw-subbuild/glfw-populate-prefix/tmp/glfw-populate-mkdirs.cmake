# Distributed under the OSI-approved BSD 3-Clause License.  See accompanying
# file Copyright.txt or https://cmake.org/licensing for details.

cmake_minimum_required(VERSION 3.5)

file(MAKE_DIRECTORY
  "E:/apps/Closy/engine/build/_deps/glfw-src"
  "E:/apps/Closy/engine/build/_deps/glfw-build"
  "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix"
  "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix/tmp"
  "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix/src/glfw-populate-stamp"
  "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix/src"
  "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix/src/glfw-populate-stamp"
)

set(configSubDirs Debug)
foreach(subDir IN LISTS configSubDirs)
    file(MAKE_DIRECTORY "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix/src/glfw-populate-stamp/${subDir}")
endforeach()
if(cfgdir)
  file(MAKE_DIRECTORY "E:/apps/Closy/engine/build/_deps/glfw-subbuild/glfw-populate-prefix/src/glfw-populate-stamp${cfgdir}") # cfgdir has leading slash
endif()
