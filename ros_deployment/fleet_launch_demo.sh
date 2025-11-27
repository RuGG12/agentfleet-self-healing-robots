#!/bin/bash

# ==============================================================================
# fleet_launch_demo.sh
# Description: One-Click Launcher for the Multi-Agent Warehouse System.
#              Handles environment setup, cleanup, simulation spawning, and
#              orchestrator execution.
#
# Author: Rugved Raote
# Competition: Google AI Agents Intensive - Capstone
# ==============================================================================

# 1. DYNAMIC DIRECTORY SETUP
# Gets the directory where this script is located
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$PROJECT_DIR" || { echo "❌ Critical Error: Could not switch to project directory."; exit 1; }

echo ""
echo "======================================================================"
echo "   AGENT FLEET DEMO - LAUNCH SEQUENCE"
echo "======================================================================"
echo "📂 Project Directory: $PROJECT_DIR"

# 2. API KEY HANDLER
# Checks for env variable, prompts if missing. NEVER hardcodes.
if [ -z "$GOOGLE_API_KEY" ]; then
    echo ""
    echo "⚠️  GOOGLE_API_KEY not found in environment variables."
    echo -n "🔑 Please enter your Google API Key to proceed: "
    read -r USER_KEY
    
    if [ -z "$USER_KEY" ]; then
        echo "❌ Error: API Key is required to run the agents."
        exit 1
    fi
    export GOOGLE_API_KEY="$USER_KEY"
    echo "✓ API Key exported for this session."
else
    echo "✓ GOOGLE_API_KEY found in environment."
fi

# 3. ROS2 ENVIRONMENT SETUP
echo ""
echo "🛠️  Setting up ROS2 environment..."
source /opt/ros/humble/setup.bash
export TURTLEBOT3_MODEL=burger
export GAZEBO_MODEL_PATH=$GAZEBO_MODEL_PATH:/opt/ros/humble/share/turtlebot3_description/models

# 4. CLEANUP OLD PROCESSES
echo "🧹 Cleaning up old simulation processes..."
killall -9 gzserver gzclient gazebo robot_state_publisher 2> /dev/null
sleep 2

# 5. LAUNCH GAZEBO
echo "🌍 Launching Gazebo World..."
ros2 launch turtlebot3_gazebo empty_world.launch.py > /dev/null 2>&1 &
GAZEBO_PID=$!

echo "⏳ Waiting 8 seconds for Gazebo to initialize..."
sleep 8

# 6. SPAWN VISUALS (Walls & Sticky Zone)
echo "🎨 Painting the arena..."
python3 spawn_visuals.py
sleep 2

# 7. SPAWN ROBOTS
echo "🤖 Spawning Robot Fleet..."
python3 spawn_fleet.py

echo "⏳ Waiting 5 seconds for physics to settle..."
sleep 5

# 8. LAUNCH ORCHESTRATOR
echo ""
echo "======================================================================"
echo "🚀 STARTING FLEET ORCHESTRATOR"
echo "   NOTE: Switch to your Gazebo window to see the robot actions."
echo "======================================================================"

python3 fleet_orchestrator.py

# 9. EXIT HANDLER
echo ""
echo "🛑 Demo Finished. Shutting down..."
kill $GAZEBO_PID
pkill -f gzclient
echo "✓ Shutdown complete."
