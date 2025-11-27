#!/usr/bin/env python3
"""
manager_tools.py
Description: High-level coordination tools for the Fleet Manager Agent.
             Handles task allocation, conflict detection, fleet status monitoring,
             and failure recovery. Does NOT directly control robot hardware.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import threading
from typing import Dict, Any, List, Optional

# --- Local Project Imports ---
from sim_tools import WarehouseSim
from observability import obs

# --- Global State Management ---
# Optimization: Global lock ensures thread-safe clearance checks when multiple
# robots request access simultaneously.
_clearance_lock = threading.Lock()

# Global task tracking (mimics persistent session state)
# Structure: {robot_id: {"target": [x,y], "status": "assigned|active|complete|failed"}}
_active_tasks = {}
_task_queue = []


# ==============================================================================
# FLEET OBSERVABILITY TOOLS
#Description: Allows the Manager to see the big picture.
# ==============================================================================

def get_fleet_status() -> Dict[str, Any]:
    """
    Get the current status of all robots in the fleet.
    
    Returns:
        Dict: {
            "robots": {id: status...},
            "active_tasks": {...},
            "pending_tasks": int
        }
    """
    sim = WarehouseSim()
    robot_states = sim.get_all_robot_paths()
    
    return {
        "robots": robot_states,
        "active_tasks": _active_tasks,
        "pending_tasks": len([t for t in _task_queue if t["assigned_to"] is None])
    }


def get_idle_robots() -> Dict[str, Any]:
    """
    Get a list of all robots currently available for new tasks.
    
    Optimization:
    Fixes stale status issues by checking if a robot is physically at its target,
    even if the paperwork hasn't been updated yet.
    
    Returns:
        Dict: {"idle_count": int, "idle_robots": {id: location...}}
    """
    sim = WarehouseSim()
    robot_states = sim.get_all_robot_paths()
    
    idle_robots = {}
    for robot_id, state in robot_states.items():
        # Only consider robots that are physically stopped
        if state["status"] == "IDLE":
            is_available = False
            
            # Condition 1: No task assigned at all
            if robot_id not in _active_tasks:
                is_available = True
            
            # Condition 2: Task is explicitly marked done in paperwork
            elif _active_tasks[robot_id]["status"] in ["complete", "failed"]:
                is_available = True
                
            # Condition 3 (The Fix): Robot is at target but status wasn't updated
            elif state["current"] == state["target"]:
                is_available = True
            
            if is_available:
                idle_robots[robot_id] = {
                    "position": state["current"],
                    "available": True
                }
    
    return {
        "idle_count": len(idle_robots),
        "idle_robots": idle_robots
    }


# ==============================================================================
# COORDINATION & CONTROL TOOLS
# Description: The core logic for traffic management and task assignment.
# ==============================================================================

def check_clearance(robot_id: str, target_x: int, target_y: int) -> Dict[str, Any]:
    """
    Check if a robot can safely navigate to a target.
    Acts as the "Air Traffic Control" logic.
    
    Args:
        robot_id (str): ID of requesting robot.
        target_x (int): Target X coordinate.
        target_y (int): Target Y coordinate.
    
    Returns:
        Dict: {"clearance": "GRANTED"|"DENIED", "reason": str}
    """
    with _clearance_lock:  # Thread safety optimization
        sim = WarehouseSim()
        target = [target_x, target_y]
        
        # 1. Check logical conflicts (Active Tasks)
        # Prevents race conditions where two robots target the same spot
        for other_id, task in _active_tasks.items():
            if other_id != robot_id and task["target"] == target:
                if task["status"] not in ["complete", "failed"]:
                    return {
                        "clearance": "DENIED", 
                        "reason": f"Target ({target_x}, {target_y}) already assigned to {other_id}",
                        "robot_id": robot_id,
                        "target": target
                    }
        
        # 2. Check physical conflicts (Simulation Path)
        has_conflict = sim.check_path_conflict(robot_id, target)
        
        if has_conflict:
            return {
                "clearance": "DENIED",
                "reason": f"Conflict detected: Another robot is using/targeting ({target_x}, {target_y})",
                "robot_id": robot_id,
                "target": target
            }
        
        # 3. Pre-reserve the target
        if robot_id not in _active_tasks or _active_tasks[robot_id]["status"] in ["complete", "failed"]:
            _active_tasks[robot_id] = {
                "task_id": f"pending_{robot_id}",
                "target": target,
                "status": "pending"
            }

        obs.log_event("Manager", "Clearance_Check", metadata={
            "robot_id": robot_id, 
            "decision": "GRANTED"
        })
        
        return {
            "clearance": "GRANTED",
            "reason": "No conflicts detected. Safe to proceed.",
            "robot_id": robot_id,
            "target": target
        }


def assign_task_to_robot(robot_id: str, target_x: int, target_y: int, task_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Assign a delivery task to a specific robot.
    
    Args:
        robot_id (str): ID of the robot.
        target_x (int): Destination X.
        target_y (int): Destination Y.
        task_id (str, optional): Custom ID.
    
    Returns:
        Dict: Confirmation of assignment or failure reason.
    """
    sim = WarehouseSim()
    robot_states = sim.get_all_robot_paths()
    
    # Validation
    if robot_id not in robot_states:
        return {"status": "FAILED", "reason": f"Robot {robot_id} does not exist"}
    
    if robot_states[robot_id]["status"] != "IDLE":
        return {"status": "FAILED", "reason": f"Robot {robot_id} is currently {robot_states[robot_id]['status']}"}
    
    # Assignment
    task_id = task_id or f"task_{robot_id}_{target_x}_{target_y}"
    _active_tasks[robot_id] = {
        "task_id": task_id,
        "target": [target_x, target_y],
        "status": "assigned"
    }
    
    obs.log_event("Manager", "Task_Assigned", metadata={
        "robot_id": robot_id,
        "task_id": task_id,
        "target": [target_x, target_y]
    })
    
    return {
        "status": "SUCCESS",
        "robot_id": robot_id,
        "task_id": task_id,
        "target": [target_x, target_y],
        "message": f"Task {task_id} assigned to {robot_id}: deliver to ({target_x}, {target_y})"
    }


def mark_task_complete(robot_id: str, success: bool = True) -> Dict[str, Any]:
    """
    Update the status of an active task to complete or failed.
    
    Args:
        robot_id (str): Robot reporting the status.
        success (bool): Outcome of the task.
    
    Returns:
        Dict: Updated status information.
    """
    if robot_id not in _active_tasks:
        return {"status": "ERROR", "reason": f"No active task found for {robot_id}"}
    
    task = _active_tasks[robot_id]
    old_status = task["status"]
    task["status"] = "complete" if success else "failed"
    
    status_str = "completed successfully" if success else "FAILED"
    
    return {
        "status": "SUCCESS",
        "robot_id": robot_id,
        "task_id": task["task_id"],
        "previous_status": old_status,
        "new_status": task["status"],
        "message": f"Task {task['task_id']} for {robot_id} {status_str}"
    }


# ==============================================================================
# RECOVERY TOOLS
# Description: Handling failure scenarios.
# ==============================================================================

def reallocate_failed_task(failed_robot_id: str) -> Dict[str, Any]:
    """
    Reallocate a failed task to the nearest available idle robot.
    
    Args:
        failed_robot_id (str): The robot that couldn't complete the task.
    
    Returns:
        Dict: Details of the reallocation (new robot, new task ID).
    """
    if failed_robot_id not in _active_tasks:
        return {"status": "ERROR", "reason": f"No task found for {failed_robot_id}"}
    
    failed_task = _active_tasks[failed_robot_id]
    target = failed_task["target"]
    
    # 1. Find candidates
    idle_result = get_idle_robots()
    idle_robots = idle_result["idle_robots"]
    
    if not idle_robots:
        return {
            "status": "FAILED",
            "reason": "No idle robots available for reallocation",
            "failed_task": failed_task
        }
    
    # 2. Select best candidate (Nearest Neighbor)
    closest_robot = None
    min_distance = float('inf')
    
    for robot_id, info in idle_robots.items():
        if robot_id == failed_robot_id:
            continue  # Don't reassign to self
        
        pos = info["position"]
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        
        if distance < min_distance:
            min_distance = distance
            closest_robot = robot_id
    
    if not closest_robot:
        return {"status": "FAILED", "reason": "No suitable robot found for reallocation"}
    
    # 3. Assign
    assignment_result = assign_task_to_robot(
        closest_robot, 
        target[0], 
        target[1],
        task_id=failed_task["task_id"] + "_retry"
    )
    
    return {
        "status": "SUCCESS",
        "original_robot": failed_robot_id,
        "new_robot": closest_robot,
        "task_id": assignment_result["task_id"],
        "target": target,
        "message": f"Task reallocated from {failed_robot_id} to {closest_robot}"
    }


def reset_task_state():
    """Reset all task tracking. Useful for clean restarts between demos."""
    global _active_tasks, _task_queue
    _active_tasks = {}
    _task_queue = []
    return {"status": "SUCCESS", "message": "Task state reset"}