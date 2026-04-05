cmake_minimum_required(VERSION 3.16)
project(ClosyEngine LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

add_library(closy_avatar STATIC
  src/Avatar.cpp
  src/AvatarPose.cpp
  src/Mesh.cpp
  src/Scene.cpp
  src/avatar_demo_outfit.cpp
  src/outfit_builder.cpp
)

target_include_directories(closy_avatar
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

include(FetchContent)
FetchContent_Declare(
  glm
  GIT_REPOSITORY https://github.com/g-truc/glm.git
  GIT_TAG        1.0.1
)
FetchContent_MakeAvailable(glm)

target_link_libraries(closy_avatar PUBLIC glm::glm)

add_executable(avatar_smoke tests/avatar_smoke.cpp)
target_link_libraries(avatar_smoke PRIVATE closy_avatar)

add_library(closy_gl STATIC
  src/gl_procs.cpp
  src/GlRenderer.cpp
  src/OffscreenCapture.cpp
  src/write_png.cpp
)

target_include_directories(closy_gl
  PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party
)

target_link_libraries(closy_gl PUBLIC closy_avatar glm::glm)

option(CLOSY_BUILD_AVATAR_DEMO "Build OpenGL + GLFW viewport demo" ON)

if(CLOSY_BUILD_AVATAR_DEMO)
  FetchContent_Declare(
    glfw
    GIT_REPOSITORY https://github.com/glfw/glfw.git
    GIT_TAG        3.4
  )
  set(GLFW_BUILD_DOCS OFF CACHE BOOL "" FORCE)
  set(GLFW_BUILD_TESTS OFF CACHE BOOL "" FORCE)
  set(GLFW_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
  FetchContent_MakeAvailable(glfw)

  add_executable(avatar_viewport examples/avatar_viewport.cpp)
  target_link_libraries(avatar_viewport PRIVATE closy_gl glfw)

  add_executable(avatar_export
    examples/avatar_export.cpp
    examples/outfit_json_parse.cpp
  )
  target_include_directories(avatar_export PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/third_party
  )
  target_link_libraries(avatar_export PRIVATE closy_gl glfw)

  if(WIN32)
    target_link_libraries(avatar_viewport PRIVATE opengl32)
    target_link_libraries(avatar_export PRIVATE opengl32)
  elseif(APPLE)
    target_link_libraries(avatar_viewport PRIVATE "-framework OpenGL")
    target_link_libraries(avatar_export PRIVATE "-framework OpenGL")
  else()
    target_link_libraries(avatar_viewport PRIVATE OpenGL)
    target_link_libraries(avatar_export PRIVATE OpenGL)
  endif()
endif()
