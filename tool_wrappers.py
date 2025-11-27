#!/usr/bin/env python3
"""
tool_wrappers.py
Description: ADK-compatible wrapper functions for the backend simulation tools.
             Exposes Navigation, Status, Recovery, and Coordination capabilities
             as executable tools for the Agent Fleet.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from typing import Dict, Any, List

# --- ADK Imports ---
from google.adk.tools import FunctionTool, load_memory

# --- Local Simulation Imports ---
from sim_tools import (
    WarehouseSim, 
    Navigator as SimNavigator, 
    Critic as SimCritic, 
    Recovery as SimRecovery
)

# --- ROS Integration (Commented out for Sim Track) ---
# from ros_tools import Navigator as RosNavigator, Critic as RosCritic, Recovery as RosRecovery

# --- Optimization Notes ---
# 1. Memory Integration: Fixed import of `load_memory` from `google.adk.tools` 
#    to ensure agents can correctly access persistent session data.
# 2. Type Consistency: All tools now return Dict[str, Any] to ensure 
#    JSON-serializable responses for the LLM.
# --------------------------

# Initialize singleton simulator instance
_sim = WarehouseSim()


# ==============================================================================
# NAVIGATION TOOLS
# Description: Commands to move robots to specific coordinates.
# ==============================================================================

def navigate_robot_1(x: float, y: float) -> Dict[str, Any]:
    """
    Command robot_1 to navigate to a specific (x, y) grid position.
    Non-blocking: sets the target and returns immediately.
    
    Args:
        x (float): Target X coordinate (0-10).
        y (float): Target Y coordinate (0-10).
    
    Returns:
        Dict: Status message indicating navigation started.
    """
    nav = SimNavigator("robot_1")
    # nav = RosNavigator("robot_1") # Toggle for Real ROS 2
    return nav.go_to_pose(x, y)


def navigate_robot_2(x: float, y: float) -> Dict[str, Any]:
    """
    Command robot_2 to navigate to a specific (x, y) grid position.
    
    Args:
        x (float): Target X coordinate (0-10).
        y (float): Target Y coordinate (0-10).
    
    Returns:
        Dict: Status message indicating navigation started.
    """
    nav = SimNavigator("robot_2")
    # nav = RosNavigator("robot_2")
    return nav.go_to_pose(x, y)


def navigate_robot_3(x: float, y: float) -> Dict[str, Any]:
    """
    Command robot_3 to navigate to a specific (x, y) grid position.
    
    Args:
        x (float): Target X coordinate (0-10).
        y (float): Target Y coordinate (0-10).
    
    Returns:
        Dict: Status message indicating navigation started.
    """
    nav = SimNavigator("robot_3")
    # nav = RosNavigator("robot_3")
    return nav.go_to_pose(x, y)


# ==============================================================================
# STATUS TOOLS
# Description: Observability tools for agents to check their own state.
# ==============================================================================

def check_status_robot_1() -> Dict[str, Any]:
    """
    Check the current status and position of robot_1.
    
    Returns:
        Dict: Contains keys 'state' (IDLE/NAVIGATING/STUCK), 'pose', and 'target'.
    """
    critic = SimCritic("robot_1")
    return critic.get_status()


def check_status_robot_2() -> Dict[str, Any]:
    """
    Check the current status and position of robot_2.
    
    Returns:
        Dict: Contains keys 'state' (IDLE/NAVIGATING/STUCK), 'pose', and 'target'.
    """
    critic = SimCritic("robot_2")
    return critic.get_status()


def check_status_robot_3() -> Dict[str, Any]:
    """
    Check the current status and position of robot_3.
    
    Returns:
        Dict: Contains keys 'state' (IDLE/NAVIGATING/STUCK), 'pose', and 'target'.
    """
    critic = SimCritic("robot_3")
    return critic.get_status()


# ==============================================================================
# RECOVERY TOOLS
# Description: specialized maneuvers for getting unstuck.
# ==============================================================================

def recover_robot_1(strategy: str) -> Dict[str, Any]:
    """
    Execute a recovery maneuver for robot_1 when STUCK.
    
    Args:
        strategy (str): Strategy name. Options:
            - 'reverse_and_turn_left'
            - 'reverse_and_turn_right'
            - 'forward_left'
            - 'reverse_only'
    
    Returns:
        Dict: Status of the recovery attempt.
    """
    recovery = SimRecovery("robot_1")
    return recovery.execute_recovery(strategy)


def recover_robot_2(strategy: str) -> Dict[str, Any]:
    """
    Execute a recovery maneuver for robot_2 when STUCK.
    
    Args:
        strategy (str): Strategy name (see recover_robot_1 for options).
    
    Returns:
        Dict: Status of the recovery attempt.
    """
    recovery = SimRecovery("robot_2")
    return recovery.execute_recovery(strategy)


def recover_robot_3(strategy: str) -> Dict[str, Any]:
    """
    Execute a recovery maneuver for robot_3 when STUCK.
    
    Args:
        strategy (str): Strategy name (see recover_robot_1 for options).
    
    Returns:
        Dict: Status of the recovery attempt.
    """
    recovery = SimRecovery("robot_3")
    return recovery.execute_recovery(strategy)


# ==============================================================================
# COORDINATION & SIMULATION TOOLS
# Description: Global tools for the Manager Agent and Orchestrator.
# ==============================================================================

def check_path_conflict(robot_id: str, target_x: int, target_y: int) -> Dict[str, Any]:
    """
    Check if a proposed navigation target would conflict with other robots.
    Used by Manager Agent to grant/deny clearance.
    
    Args:
        robot_id (str): 'robot_1', 'robot_2', or 'robot_3'.
        target_x (int): Proposed X coordinate.
        target_y (int): Proposed Y coordinate.
    
    Returns:
        Dict: {
            "conflict": bool,
            "message": str
        }
    """
    conflict = _sim.check_path_conflict(robot_id, [target_x, target_y])
    
    if conflict:
        return {
            "conflict": True,
            "message": f"CONFLICT: Another robot is using or heading to ({target_x}, {target_y})"
        }
    else:
        return {
            "conflict": False,
            "message": f"CLEAR: Path to ({target_x}, {target_y}) is available"
        }


def get_all_robot_states() -> Dict[str, Dict[str, Any]]:
    """
    Get the current state of the entire fleet.
    
    Returns:
        Dict: Mapping of robot_id -> {pose, target, status}.
    """
    return _sim.get_all_robot_paths()


def tick_simulation() -> Dict[str, Any]:
    """
    Advance the simulation by one time step.
    CRITICAL: Updates positions for all robots based on current velocities.
    
    Returns:
        Dict: {
            "status": "tick_complete",
            "robot_states": ...
        }
    """
    _sim.tick()
    states = _sim.get_all_robot_paths()
    return {
        "status": "tick_complete",
        "robot_states": states
    }


# ==============================================================================
# ADK TOOL FACTORY
# ==============================================================================

def get_robot_tools(robot_id: str):
    """
    Factory function to retrieve the specific toolset for a given robot.
    Wraps python functions into ADK FunctionTool objects.
    
    Args:
        robot_id (str): 'robot_1', 'robot_2', or 'robot_3'
    
    Returns:
        tuple: (FunctionTool(nav), FunctionTool(status), FunctionTool(recovery), load_memory)
    """
    tool_map = {
        "robot_1": (navigate_robot_1, check_status_robot_1, recover_robot_1),
        "robot_2": (navigate_robot_2, check_status_robot_2, recover_robot_2),
        "robot_3": (navigate_robot_3, check_status_robot_3, recover_robot_3),
    }
    
    if robot_id not in tool_map:
        raise ValueError(f"Unknown robot_id: {robot_id}. Must be 'robot_1', 'robot_2', or 'robot_3'")
    
    nav_func, status_func, recovery_func = tool_map[robot_id]
    
    return (
        FunctionTool(nav_func),
        FunctionTool(status_func),
        FunctionTool(recovery_func),
        load_memory  # Fixed: using correctly imported ADK memory tool
    )