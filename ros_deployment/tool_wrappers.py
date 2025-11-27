#!/usr/bin/env python3
"""
tool_wrappers.py
Description: Wrappers for ADK tools to interface with ROS2 and Simulation.
             Ensures correct linking between the Agent Logic and the ROS Logic.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from typing import Dict, Any

# --- ADK Imports ---
from google.adk.tools import FunctionTool, load_memory

# --- Local Project Imports ---
from sim_tools import WarehouseSim 
# CRITICAL: We must use ROS tools for the actual agents
from ros_tools import Navigator as RosNavigator, Critic as RosCritic, Recovery as RosRecovery

# Initialize the singleton simulator (Only used for checking path conflicts, not status)
_sim = WarehouseSim()

# =========================================================
# PHASE 1: NAVIGATION TOOLS (ROS)
# =========================================================

def navigate_robot_1(x: float, y: float) -> Dict[str, Any]:
    return RosNavigator("robot_1").go_to_pose(x, y)

def navigate_robot_2(x: float, y: float) -> Dict[str, Any]:
    return RosNavigator("robot_2").go_to_pose(x, y)

def navigate_robot_3(x: float, y: float) -> Dict[str, Any]:
    return RosNavigator("robot_3").go_to_pose(x, y)

# =========================================================
# PHASE 2: STATUS CHECKING TOOLS (ROS)
# =========================================================

def check_status_robot_1() -> Dict[str, Any]:
    return RosCritic("robot_1").get_status()

def check_status_robot_2() -> Dict[str, Any]:
    return RosCritic("robot_2").get_status()

def check_status_robot_3() -> Dict[str, Any]:
    return RosCritic("robot_3").get_status()

# =========================================================
# PHASE 3: RECOVERY TOOLS (ROS)
# =========================================================

def recover_robot_1(strategy: str) -> Dict[str, Any]:
    return RosRecovery("robot_1").execute_recovery(strategy)

def recover_robot_2(strategy: str) -> Dict[str, Any]:
    return RosRecovery("robot_2").execute_recovery(strategy)

def recover_robot_3(strategy: str) -> Dict[str, Any]:
    return RosRecovery("robot_3").execute_recovery(strategy)

# =========================================================
# PHASE 4: COORDINATION TOOLS (Logic/Sim Only)
# =========================================================

def check_path_conflict(robot_id: str, target_x: int, target_y: int) -> Dict[str, Any]:
    conflict = _sim.check_path_conflict(robot_id, [target_x, target_y])
    if conflict:
        return {"conflict": True, "message": f"CONFLICT: Target ({target_x}, {target_y}) busy"}
    return {"conflict": False, "message": "CLEAR"}

def get_all_robot_states() -> Dict[str, Dict[str, Any]]:
    return _sim.get_all_robot_paths()

def tick_simulation() -> Dict[str, Any]:
    # In ROS, time ticks itself. We just keep this for compatibility.
    return {"status": "tick_ignored_using_ros", "robot_states": {}}

# --- Utility ---

def get_robot_tools(robot_id: str):
    tool_map = {
        "robot_1": (navigate_robot_1, check_status_robot_1, recover_robot_1),
        "robot_2": (navigate_robot_2, check_status_robot_2, recover_robot_2),
        "robot_3": (navigate_robot_3, check_status_robot_3, recover_robot_3),
    }
    if robot_id not in tool_map:
        raise ValueError(f"Unknown robot_id: {robot_id}")
    
    nav_func, status_func, recovery_func = tool_map[robot_id]
    
    return (
        FunctionTool(nav_func),
        FunctionTool(status_func),
        FunctionTool(recovery_func),
        load_memory
    )
