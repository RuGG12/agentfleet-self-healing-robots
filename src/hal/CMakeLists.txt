cmake_minimum_required(VERSION 3.16)
project(agentfleet_hal VERSION 1.0.0 LANGUAGES CXX)

# C++17 required for structured bindings and std::optional
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# Build type defaults to Release
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Compiler flags for optimization
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

# =============================================================================
# Dependencies
# =============================================================================

# Find Python and pybind11
find_package(Python3 REQUIRED COMPONENTS Interpreter Development)
find_package(pybind11 CONFIG REQUIRED)

# Find ROS 2 packages (optional - allows standalone build without ROS)
find_package(ament_cmake QUIET)
find_package(rclcpp QUIET)
find_package(geometry_msgs QUIET)
find_package(nav_msgs QUIET)
find_package(sensor_msgs QUIET)

if(rclcpp_FOUND)
    message(STATUS "ROS 2 found - building with full ROS support")
    set(HAS_ROS2 TRUE)
    add_definitions(-DHAS_ROS2)
else()
    message(STATUS "ROS 2 not found - building standalone mode")
    set(HAS_ROS2 FALSE)
endif()

# =============================================================================
# Library Sources
# =============================================================================

set(HAL_SOURCES
    src/robot_hal.cpp
    src/collision_checker.cpp
    src/path_smoother.cpp
)

set(HAL_HEADERS
    include/robot_hal.hpp
    include/collision_checker.hpp
    include/path_smoother.hpp
)

# =============================================================================
# Core HAL Library (static)
# =============================================================================

add_library(agentfleet_hal_core STATIC ${HAL_SOURCES})
target_include_directories(agentfleet_hal_core PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)

if(HAS_ROS2)
    # Use ament_target_dependencies for ROS 2 packages (handles linking properly)
    ament_target_dependencies(agentfleet_hal_core
        rclcpp
        geometry_msgs
        nav_msgs
        sensor_msgs
    )
endif()

# =============================================================================
# Python Bindings Module
# =============================================================================

pybind11_add_module(agentfleet_cpp MODULE src/bindings.cpp)
target_link_libraries(agentfleet_cpp PRIVATE agentfleet_hal_core)
target_include_directories(agentfleet_cpp PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

# Set output name without lib prefix on all platforms
set_target_properties(agentfleet_cpp PROPERTIES
    PREFIX ""
    OUTPUT_NAME "agentfleet_cpp"
)

# =============================================================================
# Installation
# =============================================================================

install(TARGETS agentfleet_cpp
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin
)

install(TARGETS agentfleet_hal_core
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
)

install(FILES ${HAL_HEADERS}
    DESTINATION include/agentfleet_hal
)

# =============================================================================
# Testing (optional)
# =============================================================================

option(BUILD_TESTS "Build unit tests" OFF)

if(BUILD_TESTS)
    enable_testing()
    find_package(GTest REQUIRED)
    
    add_executable(test_collision_checker tests/test_collision_checker.cpp)
    target_link_libraries(test_collision_checker 
        agentfleet_hal_core 
        GTest::gtest_main
    )
    
    add_test(NAME CollisionCheckerTest COMMAND test_collision_checker)
endif()

# =============================================================================
# Summary
# =============================================================================

message(STATUS "")
message(STATUS "=== AgentFleet HAL Build Configuration ===")
message(STATUS "  Version:      ${PROJECT_VERSION}")
message(STATUS "  Build type:   ${CMAKE_BUILD_TYPE}")
message(STATUS "  C++ Standard: ${CMAKE_CXX_STANDARD}")
message(STATUS "  Python:       ${Python3_VERSION}")
message(STATUS "  pybind11:     ${pybind11_VERSION}")
message(STATUS "  ROS 2:        ${HAS_ROS2}")
message(STATUS "")
