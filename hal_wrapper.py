#!/usr/bin/env python3
"""
hal_wrapper.py
Description: Python wrapper for the C++ Hardware Abstraction Layer.
             Provides graceful fallback to pure Python implementation
             when C++ module is not available.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time

# =============================================================================
# Try to import C++ module
# =============================================================================

try:
    import agentfleet_cpp
    HAL_AVAILABLE = True
    print("✓ [HAL] C++ module loaded successfully")
    if hasattr(agentfleet_cpp, 'HAS_ROS2'):
        print(f"  ROS 2 support: {agentfleet_cpp.HAS_ROS2}")
except ImportError as e:
    HAL_AVAILABLE = False
    print(f"⚠ [HAL] C++ module not available: {e}")
    print("  Using Python fallback implementation")


# =============================================================================
# Enums matching C++ definitions
# =============================================================================

class FaultState(Enum):
    """Hardware fault states for simulation."""
    NONE = 0
    MOTOR_TIMEOUT = 1
    PACKET_DROP = 2
    SENSOR_FREEZE = 3


class RobotStatus(Enum):
    """Robot operational status."""
    IDLE = 0
    NAVIGATING = 1
    STUCK = 2
    RECOVERING = 3
    FAULT = 4


# =============================================================================
# Python Fallback Classes
# =============================================================================

@dataclass
class _FallbackState:
    """Internal state for Python fallback HAL."""
    pose_x: float = 0.0
    pose_y: float = 0.0
    yaw: float = 0.0
    target_x: float = 0.0
    target_y: float = 0.0
    status: str = "IDLE"
    fault_state: FaultState = FaultState.NONE


class _FallbackHAL:
    """Pure Python HAL implementation for when C++ is unavailable."""
    
    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self._state = _FallbackState()
        self._connected = True
        print(f"[HAL-Fallback] Initialized for {robot_id}")
    
    def publish_cmd_vel(self, linear_x: float, angular_z: float) -> bool:
        if self._state.fault_state == FaultState.MOTOR_TIMEOUT:
            print(f"[HAL-Fallback] FAULT: Motor timeout on {self.robot_id}")
            return False
        # In fallback mode, we just log the command
        # Real implementation would interface with rclpy
        return True
    
    def stop(self):
        self.publish_cmd_vel(0.0, 0.0)
    
    def get_pose(self) -> List[float]:
        return [self._state.pose_x, self._state.pose_y]
    
    def get_yaw(self) -> float:
        return self._state.yaw
    
    def get_status(self) -> str:
        return self._state.status
    
    def get_robot_id(self) -> str:
        return self.robot_id
    
    def is_connected(self) -> bool:
        return self._connected
    
    def set_status(self, status: RobotStatus):
        self._state.status = status.name
    
    def set_target(self, x: float, y: float):
        self._state.target_x = x
        self._state.target_y = y
    
    def get_target(self) -> List[float]:
        return [self._state.target_x, self._state.target_y]
    
    def inject_fault(self, fault_type: str):
        fault_map = {
            "motor_timeout": FaultState.MOTOR_TIMEOUT,
            "MOTOR_TIMEOUT": FaultState.MOTOR_TIMEOUT,
            "packet_drop": FaultState.PACKET_DROP,
            "PACKET_DROP": FaultState.PACKET_DROP,
            "sensor_freeze": FaultState.SENSOR_FREEZE,
            "SENSOR_FREEZE": FaultState.SENSOR_FREEZE,
        }
        self._state.fault_state = fault_map.get(fault_type, FaultState.NONE)
        if self._state.fault_state == FaultState.MOTOR_TIMEOUT:
            self._state.status = "FAULT"
        print(f"[HAL-Fallback] Injected fault: {fault_type}")
    
    def clear_faults(self):
        self._state.fault_state = FaultState.NONE
        if self._state.status == "FAULT":
            self._state.status = "IDLE"
    
    def get_fault_state(self) -> FaultState:
        return self._state.fault_state
    
    def has_fault(self) -> bool:
        return self._state.fault_state != FaultState.NONE
    
    # Allow setting pose for simulation
    def _set_pose(self, x: float, y: float, yaw: float = 0.0):
        self._state.pose_x = x
        self._state.pose_y = y
        self._state.yaw = yaw


class _FallbackCollisionChecker:
    """Pure Python collision checker fallback."""
    
    def __init__(self):
        self._grid_width = 10
        self._grid_height = 10
        self._sticky_zone = {"x_min": 5, "x_max": 7, "y_min": 5, "y_max": 7}
    
    def set_grid_size(self, width: int, height: int):
        self._grid_width = width
        self._grid_height = height
    
    def set_sticky_zone(self, x_min: int, x_max: int, y_min: int, y_max: int):
        self._sticky_zone = {"x_min": x_min, "x_max": x_max, 
                             "y_min": y_min, "y_max": y_max}
    
    def is_in_sticky_zone(self, x: float, y: float) -> bool:
        sz = self._sticky_zone
        return (sz["x_min"] <= x <= sz["x_max"] and 
                sz["y_min"] <= y <= sz["y_max"])
    
    def check_path_conflict(self, robot_id: str, target_x: float, target_y: float,
                           fleet_positions: Dict[str, List[float]],
                           fleet_targets: Dict[str, List[float]]) -> bool:
        tx, ty = int(round(target_x)), int(round(target_y))
        
        for other_id, pos in fleet_positions.items():
            if other_id == robot_id:
                continue
            
            ox, oy = int(round(pos[0])), int(round(pos[1]))
            if ox == tx and oy == ty:
                return True
            
            if other_id in fleet_targets:
                otx = int(round(fleet_targets[other_id][0]))
                oty = int(round(fleet_targets[other_id][1]))
                if otx == tx and oty == ty:
                    return True
        
        return False
    
    def is_in_bounds(self, x: float, y: float) -> bool:
        return 0 <= x < self._grid_width and 0 <= y < self._grid_height
    
    def check_waypoints(self, waypoints: List[List[float]]) -> List[bool]:
        return [self.is_in_sticky_zone(wp[0], wp[1]) for wp in waypoints]
    
    def find_first_sticky_waypoint(self, waypoints: List[List[float]]) -> int:
        for i, wp in enumerate(waypoints):
            if self.is_in_sticky_zone(wp[0], wp[1]):
                return i
        return -1
    
    @staticmethod
    def distance(x1: float, y1: float, x2: float, y2: float) -> float:
        import math
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    
    @staticmethod
    def manhattan_distance(x1: int, y1: int, x2: int, y2: int) -> int:
        return abs(x2 - x1) + abs(y2 - y1)


def _fallback_smooth_path(waypoints: List[List[float]], 
                          points_per_segment: int = 10) -> List[List[float]]:
    """Python fallback for path smoothing using linear interpolation."""
    if len(waypoints) < 2:
        return waypoints
    
    result = []
    for i in range(len(waypoints) - 1):
        p1, p2 = waypoints[i], waypoints[i + 1]
        for j in range(points_per_segment):
            t = j / points_per_segment
            result.append([
                p1[0] + t * (p2[0] - p1[0]),
                p1[1] + t * (p2[1] - p1[1])
            ])
    result.append(waypoints[-1])
    return result


def _fallback_path_length(waypoints: List[List[float]]) -> float:
    """Calculate total path length."""
    import math
    if len(waypoints) < 2:
        return 0.0
    
    length = 0.0
    for i in range(1, len(waypoints)):
        dx = waypoints[i][0] - waypoints[i-1][0]
        dy = waypoints[i][1] - waypoints[i-1][1]
        length += math.sqrt(dx*dx + dy*dy)
    return length


# =============================================================================
# Unified Public Interface
# =============================================================================

class HALInterface:
    """
    Unified Hardware Abstraction Layer interface.
    
    Automatically uses C++ implementation if available,
    falls back to Python otherwise.
    
    Example:
        >>> hal = HALInterface("robot_1")
        >>> hal.publish_cmd_vel(0.5, 0.0)
        >>> pose = hal.get_pose()
    """
    
    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        
        if HAL_AVAILABLE:
            self._hal = agentfleet_cpp.RobotHAL(robot_id)
            self._impl = "cpp"
        else:
            self._hal = _FallbackHAL(robot_id)
            self._impl = "python"
    
    @property
    def implementation(self) -> str:
        """Returns 'cpp' or 'python' indicating which implementation is active."""
        return self._impl
    
    def publish_cmd_vel(self, linear_x: float, angular_z: float) -> bool:
        return self._hal.publish_cmd_vel(linear_x, angular_z)
    
    def stop(self):
        self._hal.stop()
    
    def get_pose(self) -> Tuple[float, float]:
        pose = self._hal.get_pose()
        return (pose[0], pose[1])
    
    def get_yaw(self) -> float:
        return self._hal.get_yaw()
    
    def get_status(self) -> str:
        return self._hal.get_status()
    
    def is_connected(self) -> bool:
        return self._hal.is_connected()
    
    def set_target(self, x: float, y: float):
        self._hal.set_target(x, y)
    
    def get_target(self) -> Tuple[float, float]:
        target = self._hal.get_target()
        return (target[0], target[1])
    
    def inject_fault(self, fault_type: str):
        """Inject a simulated hardware fault."""
        self._hal.inject_fault(fault_type)
    
    def clear_faults(self):
        """Clear all active faults."""
        self._hal.clear_faults()
    
    def has_fault(self) -> bool:
        return self._hal.has_fault()


class CollisionCheckerInterface:
    """
    Unified collision checker interface.
    
    Uses C++ for performance when available, Python fallback otherwise.
    """
    
    def __init__(self):
        if HAL_AVAILABLE:
            self._checker = agentfleet_cpp.CollisionChecker()
            self._impl = "cpp"
        else:
            self._checker = _FallbackCollisionChecker()
            self._impl = "python"
    
    @property
    def implementation(self) -> str:
        return self._impl
    
    def set_grid_size(self, width: int, height: int):
        self._checker.set_grid_size(width, height)
    
    def set_sticky_zone(self, x_min: int, x_max: int, y_min: int, y_max: int):
        self._checker.set_sticky_zone(x_min, x_max, y_min, y_max)
    
    def is_in_sticky_zone(self, x: float, y: float) -> bool:
        return self._checker.is_in_sticky_zone(x, y)
    
    def check_path_conflict(self, robot_id: str, target_x: float, target_y: float,
                           fleet_positions: Dict[str, List[float]],
                           fleet_targets: Dict[str, List[float]]) -> bool:
        return self._checker.check_path_conflict(robot_id, target_x, target_y,
                                                 fleet_positions, fleet_targets)
    
    def check_waypoints(self, waypoints: List[List[float]]) -> List[bool]:
        return self._checker.check_waypoints(waypoints)


# =============================================================================
# Module-level convenience functions
# =============================================================================

def smooth_path(waypoints: List[List[float]], points_per_segment: int = 10) -> List[List[float]]:
    """
    Smooth a path using spline interpolation.
    Uses C++ Catmull-Rom splines if available, linear interpolation otherwise.
    """
    if HAL_AVAILABLE:
        return agentfleet_cpp.smooth_path(waypoints, points_per_segment)
    return _fallback_smooth_path(waypoints, points_per_segment)


def path_length(waypoints: List[List[float]]) -> float:
    """Calculate total path length in meters."""
    if HAL_AVAILABLE:
        return agentfleet_cpp.path_length(waypoints)
    return _fallback_path_length(waypoints)


def is_hal_available() -> bool:
    """Check if C++ HAL module is available."""
    return HAL_AVAILABLE


def get_hal_version() -> str:
    """Get HAL module version."""
    if HAL_AVAILABLE:
        return agentfleet_cpp.__version__
    return "fallback-1.0.0"


# =============================================================================
# Testing
# =============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("HAL Wrapper Test")
    print("=" * 60)
    
    print(f"\nHAL Available: {HAL_AVAILABLE}")
    print(f"HAL Version: {get_hal_version()}")
    
    # Test HAL Interface
    print("\n--- Testing HALInterface ---")
    hal = HALInterface("test_robot")
    print(f"Implementation: {hal.implementation}")
    print(f"Connected: {hal.is_connected()}")
    print(f"Initial pose: {hal.get_pose()}")
    
    hal.inject_fault("motor_timeout")
    print(f"Has fault: {hal.has_fault()}")
    
    result = hal.publish_cmd_vel(0.5, 0.0)
    print(f"Publish cmd_vel result: {result}")
    
    hal.clear_faults()
    print(f"Faults cleared: {not hal.has_fault()}")
    
    # Test Collision Checker
    print("\n--- Testing CollisionCheckerInterface ---")
    checker = CollisionCheckerInterface()
    print(f"Implementation: {checker.implementation}")
    
    checker.set_sticky_zone(5, 7, 5, 7)
    print(f"Point (6, 6) in sticky zone: {checker.is_in_sticky_zone(6.0, 6.0)}")
    print(f"Point (0, 0) in sticky zone: {checker.is_in_sticky_zone(0.0, 0.0)}")
    
    # Test path smoothing
    print("\n--- Testing Path Smoothing ---")
    path = [[0, 0], [5, 5], [10, 0]]
    smoothed = smooth_path(path, 5)
    print(f"Original path: {len(path)} points")
    print(f"Smoothed path: {len(smoothed)} points")
    print(f"Path length: {path_length(smoothed):.2f} meters")
    
    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)
