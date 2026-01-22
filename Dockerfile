# AgentFleet - Production Dockerfile with C++ HAL
# Competition: Agents Intensive Capstone Project 2025
# Multi-stage build for mixed Python/C++ stack

# =============================================================================
# Stage 1: C++ Builder
# =============================================================================
FROM ros:humble-ros-base AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    cmake \
    g++ \
    python3-dev \
    python3-pip \
    pybind11-dev \
    ros-humble-geometry-msgs \
    ros-humble-nav-msgs \
    ros-humble-sensor-msgs \
    && rm -rf /var/lib/apt/lists/*

# Copy HAL source code
WORKDIR /build
COPY src/hal/ ./src/hal/

# Build C++ HAL library
RUN mkdir -p build && cd build && \
    . /opt/ros/humble/setup.sh && \
    cmake ../src/hal \
    -DCMAKE_BUILD_TYPE=Release \
    -DPYTHON_EXECUTABLE=/usr/bin/python3 && \
    make -j$(nproc)

# Show build artifacts
RUN ls -la /build/build/ && \
    echo "=== HAL Build Complete ==="

# =============================================================================
# Stage 2: Runtime (ROS 2 based for C++ library support)
# =============================================================================
FROM ros:humble-ros-base AS runtime

LABEL maintainer="rugvedraote@gmail.com"
LABEL description="AgentFleet Self-Healing Robot Fleet System with C++ HAL"
LABEL version="2.0.0"

WORKDIR /app

# Install runtime dependencies (Python packages + minimal tools)
RUN apt-get update && apt-get install -y \
    python3-pip \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled C++ HAL library from builder
COPY --from=builder /build/build/agentfleet_cpp*.so /app/lib/

# Install Python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy full project
COPY . .

# Ensure lib directory is in Python path and ROS is sourced
ENV PYTHONPATH="/app/lib:/app/ros_deployment:${PYTHONPATH}"
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/agent_fleet.db

# Create data directory
RUN mkdir -p /app/data && \
    touch /app/data/agent_fleet.db

# Non-root user for security
RUN useradd -m -u 1000 agentfleet && \
    chown -R agentfleet:agentfleet /app
USER agentfleet

# Health check - verify C++ HAL is actually loadable
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD /bin/bash -c '. /opt/ros/humble/setup.sh && python3 -c "import agentfleet_cpp; print(\"HAL OK:\", agentfleet_cpp.HAS_ROS2)"' || exit 1

# Entry point sources ROS 2 environment before running Python
ENTRYPOINT ["/bin/bash", "-c", "source /opt/ros/humble/setup.sh && exec \"$@\"", "--"]
CMD ["python3", "fleet_orchestrator.py"]


# =============================================================================
# Stage 3: Lightweight Runtime (Python fallback only)
# =============================================================================
# Use this stage if you don't need C++ HAL and want a smaller image
FROM python:3.10-slim AS runtime-lite

LABEL maintainer="rugvedraote@gmail.com"
LABEL description="AgentFleet (Python-only mode, no C++ HAL)"
LABEL version="2.0.0-lite"

WORKDIR /app

RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH="/app/ros_deployment:${PYTHONPATH}"
ENV PYTHONUNBUFFERED=1
ENV DB_PATH=/app/data/agent_fleet.db

RUN mkdir -p /app/data && touch /app/data/agent_fleet.db

RUN useradd -m -u 1000 agentfleet && \
    chown -R agentfleet:agentfleet /app
USER agentfleet

CMD ["python", "fleet_orchestrator.py"]


# =============================================================================
# Stage 4: Development Image
# =============================================================================
FROM runtime AS development

USER root

RUN apt-get update && apt-get install -y \
    vim \
    curl \
    htop \
    gdb \
    && rm -rf /var/lib/apt/lists/*

USER agentfleet

CMD ["bash"]
