cmake_minimum_required(VERSION 3.10)
project(AiStreamProcessor)
include(CTest)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# 查找 FFmpeg
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED
    libavcodec
    libavformat
    libavutil
    libswscale
)

# 查找 ZeroMQ
pkg_check_modules(ZMQ REQUIRED libzmq)

# 查找 yaml-cpp
pkg_check_modules(YAMLCPP REQUIRED yaml-cpp)

# 头文件
include_directories(
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/utils
    ${CMAKE_CURRENT_SOURCE_DIR}/ai_tools
    ${CMAKE_CURRENT_SOURCE_DIR}/stream
    ${FFMPEG_INCLUDE_DIRS}
    ${ZMQ_INCLUDE_DIRS}
    ${YAMLCPP_INCLUDE_DIRS}
)

# 链接目录
link_directories(
    ${FFMPEG_LIBRARY_DIRS}
    ${ZMQ_LIBRARY_DIRS}
    ${YAMLCPP_LIBRARY_DIRS}
)

# 源文件
set(SOURCES
    main.cpp
    stream/StreamProcessor.cpp
    stream/StreamManager.cpp
    control/ControlServer.cpp
)

# 可执行文件
add_executable(ai_stream ${SOURCES})

# 定义项目根目录 (编译时注入)
target_compile_definitions(ai_stream PRIVATE
    PROJECT_SOURCE_DIR="${CMAKE_CURRENT_SOURCE_DIR}"
)

# 链接库
target_link_libraries(ai_stream
    ${FFMPEG_LIBRARIES}
    ${ZMQ_LIBRARIES}
    ${YAMLCPP_LIBRARIES}
    pthread
)

if(BUILD_TESTING)
    add_executable(ai_service_health_test tests/AiServiceHealthTest.cpp)
    target_include_directories(ai_service_health_test PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
    )
    target_link_libraries(ai_service_health_test pthread)
    add_test(NAME ai_service_health_test COMMAND ai_service_health_test)
endif()

# macOS 特殊处理
if(APPLE)
    # Homebrew 路径
    include_directories(/opt/homebrew/include)
    link_directories(/opt/homebrew/lib)
    
    # cppzmq 是 header-only，需要 zmq 库
    target_link_libraries(ai_stream zmq yaml-cpp)
endif()

# 输出信息
message(STATUS "FFmpeg include: ${FFMPEG_INCLUDE_DIRS}")
message(STATUS "FFmpeg libs: ${FFMPEG_LIBRARIES}")
message(STATUS "ZMQ include: ${ZMQ_INCLUDE_DIRS}")
message(STATUS "ZMQ libs: ${ZMQ_LIBRARIES}")
message(STATUS "YAML-CPP include: ${YAMLCPP_INCLUDE_DIRS}")
message(STATUS "YAML-CPP libs: ${YAMLCPP_LIBRARIES}")
