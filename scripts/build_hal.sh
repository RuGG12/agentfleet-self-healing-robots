#!/bin/bash
# =============================================================================
# build_hal.sh - Build C++ HAL Library Locally
# =============================================================================
# Prerequisites:
#   - CMake 3.16+
#   - C++17 compatible compiler (g++ 9+ or clang 10+)
#   - Python 3.10+ with development headers
#   - pybind11-dev package
#   - (Optional) ROS 2 Humble for full functionality
#
# Usage:
#   ./scripts/build_hal.sh [--clean] [--release|--debug]
# =============================================================================

set -e

# Navigate to project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${PROJECT_ROOT}/build"
HAL_SRC="${PROJECT_ROOT}/src/hal"

# Parse arguments
BUILD_TYPE="Release"
CLEAN_BUILD=false

for arg in "$@"; do
    case $arg in
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        --debug)
            BUILD_TYPE="Debug"
            shift
            ;;
        --release)
            BUILD_TYPE="Release"
            shift
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--clean] [--release|--debug]"
            exit 1
            ;;
    esac
done

echo "=============================================="
echo "  AgentFleet HAL Build Script"
echo "=============================================="
echo "  Project Root: ${PROJECT_ROOT}"
echo "  Build Type:   ${BUILD_TYPE}"
echo "  Clean Build:  ${CLEAN_BUILD}"
echo "=============================================="

# Clean build directory if requested
if [ "$CLEAN_BUILD" = true ] && [ -d "$BUILD_DIR" ]; then
    echo "[1/4] Cleaning build directory..."
    rm -rf "$BUILD_DIR"
fi

# Create build directory
echo "[2/4] Creating build directory..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Run CMake
echo "[3/4] Running CMake..."
cmake "$HAL_SRC" \
    -DCMAKE_BUILD_TYPE="${BUILD_TYPE}" \
    -DBUILD_TESTS=OFF

# Build
echo "[4/4] Building..."
make -j$(nproc 2>/dev/null || echo 4)

echo ""
echo "=============================================="
echo "  Build Complete!"
echo "=============================================="

# Find and display the built library
LIB_PATH=$(find "$BUILD_DIR" -name "agentfleet_cpp*.so" -o -name "agentfleet_cpp*.pyd" 2>/dev/null | head -1)
if [ -n "$LIB_PATH" ]; then
    echo "  Library: ${LIB_PATH}"
    echo ""
    echo "  To use in Python:"
    echo "    export PYTHONPATH=\"${BUILD_DIR}:\$PYTHONPATH\""
    echo "    python -c \"import agentfleet_cpp; print(agentfleet_cpp.__version__)\""
else
    echo "  Warning: Library not found in build directory"
    echo "  Check build output for errors"
fi

echo "=============================================="
