#!/usr/bin/env python3
"""
manager_tools.py
Description: Tools for the Fleet Manager Agent to coordinate multiple robots.
             Handles high-level task allocation and conflict detection.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from typing import Dict, Any, List, Optional
import threading

# --- Local Project Imports ---
from sim_tools import WarehouseSim
from observability import obs

# Add this at the top of the file, after the imports
_clearance_lock = threading.Lock()

# Global task tracking (in production, this would be in ADK session state)
_active_tasks = {}  # {robot_id: {"target": [x,y], "status": "assigned|active|complete|failed"}}
_task_queue = []    # [{"id": "task_1", "target": [x,y], "assigned_to": None}]


def get_fleet_status() -> Dict[str, Any]:
    """
    Get the current status of all robots in the fleet.
    
    Returns:
        Dictionary with robot states and active tasks
    """
    sim = WarehouseSim()
    robot_states = sim.get_all_robot_paths()
    
    return {
        "robots": robot_states,
        "active_tasks": _active_tasks,
        "pending_tasks": len([t for t in _task_queue if t["assigned_to"] is None])
    }


def check_clearance(robot_id: str, target_x: int, target_y: int) -> Dict[str, Any]:
    """
    Check if a robot can safely navigate to a target without conflicts.
    This is the "Air Traffic Control" function.
    
    Args:
        robot_id: ID of the robot requesting clearance
        target_x: Target X coordinate
        target_y: Target Y coordinate
    
    Returns:
        Dictionary with clearance decision and reason
    """
    with _clearance_lock:  # Thread safety
        sim = WarehouseSim()
        target = [target_x, target_y]
        
        # Check active tasks BEFORE checking sim conflicts
        # This prevents race conditions when multiple robots request simultaneously
        for other_id, task in _active_tasks.items():
            if other_id != robot_id and task["target"] == target:
                if task["status"] not in ["complete", "failed"]:
                    return {
                        "clearance": "DENIED", 
                        "reason": f"Target ({target_x}, {target_y}) already assigned to {other_id}",
                        "robot_id": robot_id,
                        "target": target
                    }
        
        # Check for path conflicts with other robots
        has_conflict = sim.check_path_conflict(robot_id, target)
        
        if has_conflict:
            return {
                "clearance": "DENIED",
                "reason": f"Conflict detected: Another robot is using/targeting ({target_x}, {target_y})",
                "robot_id": robot_id,
                "target": target
            }
        
        # Pre-reserve the target to prevent race conditions
        if robot_id not in _active_tasks or _active_tasks[robot_id]["status"] in ["complete", "failed"]:
            _active_tasks[robot_id] = {
                "task_id": f"pending_{robot_id}",
                "target": target,
                "status": "pending"
            }
        obs.log_event("Manager", "Clearance_Check", metadata={
            "robot_id": robot_id, 
            "decision": "GRANTED" if not has_conflict else "DENIED"
        })
        
        # All clear!
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
        robot_id: ID of the robot to assign to
        target_x: Delivery target X coordinate
        target_y: Delivery target Y coordinate
        task_id: Optional task identifier
    
    Returns:
        Dictionary confirming task assignment
    """
    sim = WarehouseSim()
    robot_states = sim.get_all_robot_paths()
    
    # Check if robot exists and is idle
    if robot_id not in robot_states:
        return {
            "status": "FAILED",
            "reason": f"Robot {robot_id} does not exist"
        }
    
    if robot_states[robot_id]["status"] != "IDLE":
        return {
            "status": "FAILED",
            "reason": f"Robot {robot_id} is currently {robot_states[robot_id]['status']}"
        }
    
    # Assign the task
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
    Mark a robot's current task as complete or failed.
    
    Args:
        robot_id: ID of the robot reporting completion
        success: True if task succeeded, False if failed
    
    Returns:
        Dictionary with task completion status
    """
    if robot_id not in _active_tasks:
        return {
            "status": "ERROR",
            "reason": f"No active task found for {robot_id}"
        }
    
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


def get_idle_robots() -> Dict[str, Any]:
    """
    Get a list of all robots that are currently idle and available for tasks.
    Detects robots that are physically idle even if task status is stale.
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
                
            # Condition 3: The robot is at its target location.
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


def reallocate_failed_task(failed_robot_id: str) -> Dict[str, Any]:
    """
    Reallocate a failed task to another idle robot.
    
    Args:
        failed_robot_id: ID of the robot that failed its task
    
    Returns:
        Dictionary with reallocation status
    """
    if failed_robot_id not in _active_tasks:
        return {
            "status": "ERROR",
            "reason": f"No task found for {failed_robot_id}"
        }
    
    failed_task = _active_tasks[failed_robot_id]
    target = failed_task["target"]
    
    # Get idle robots
    idle_result = get_idle_robots()
    idle_robots = idle_result["idle_robots"]
    
    if not idle_robots:
        return {
            "status": "FAILED",
            "reason": "No idle robots available for reallocation",
            "failed_task": failed_task
        }
    
    # Find closest idle robot (Manhattan distance)
    closest_robot = None
    min_distance = float('inf')
    
    for robot_id, info in idle_robots.items():
        if robot_id == failed_robot_id:
            continue  # Don't reassign to same robot
        
        pos = info["position"]
        distance = abs(pos[0] - target[0]) + abs(pos[1] - target[1])
        
        if distance < min_distance:
            min_distance = distance
            closest_robot = robot_id
    
    if not closest_robot:
        return {
            "status": "FAILED",
            "reason": "No suitable robot found for reallocation"
        }
    
    # Assign task to new robot
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
    """Reset all task tracking. Useful for starting new demos."""
    global _active_tasks, _task_queue
    _active_tasks = {}
    _task_queue = []
    return {"status": "SUCCESS", "message": "Task state reset"}
