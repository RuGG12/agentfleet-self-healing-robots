#!/usr/bin/env python3
"""
sim_tools.py
Description: Pure Python simulation backend for the Agent Fleet.
             Simulates a 10x10 grid warehouse with navigation logic, 
             collision detection, and a configurable "Sticky Zone" to 
             force agent failures for testing recovery.
             
             Now integrates with C++ HAL for optimized collision checking.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from typing import Dict, Any, List, Optional
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from tool_api import BaseNavigator, BaseCritic, BaseRecovery

# --- C++ HAL Integration ---
try:
    import sys
    sys.path.insert(0, './build')  # For local C++ module
    from hal_wrapper import CollisionCheckerInterface, smooth_path, is_hal_available
    USE_CPP_COLLISION = is_hal_available()
    if USE_CPP_COLLISION:
        print("[SIM] Using C++ collision checker for optimized performance")
except ImportError:
    USE_CPP_COLLISION = False
    print("[SIM] C++ HAL not available, using Python collision detection")

# --- Optimization Notes ---
# 1. Singleton Pattern: Ensures the simulation state (robot positions, obstacles)
#    remains consistent across all agent threads and the orchestration loop.
# 2. Deterministic Evaluation: The 'reset_positions' method allows the evaluation
#    script to force robots into specific starting configurations, guaranteeing
#    that they encounter the "Sticky Zone" for valid A/B testing.
# 3. C++ Integration: CollisionChecker from HAL provides ~10x faster collision
#    detection for dense path validation loops.
# --------------------------


class WarehouseSim:
    """
    Singleton simulator class representing the warehouse environment.
    Now integrates with C++ HAL for optimized collision checking.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(WarehouseSim, cls).__new__(cls)
            
            # Grid Configuration
            cls._instance.GRID_SIZE = 10
            
            # Robot State Initialization
            cls._instance.robot_states = {
                "robot_1": {"pose": [0, 0], "target": [0, 0], "status": "IDLE", "stuck_counter": 0, "recovery_cooldown": 0},
                "robot_2": {"pose": [0, 1], "target": [0, 1], "status": "IDLE", "stuck_counter": 0, "recovery_cooldown": 0},
                "robot_3": {"pose": [1, 0], "target": [1, 0], "status": "IDLE", "stuck_counter": 0, "recovery_cooldown": 0},
            }
            
            # Sticky Zone Definition (The trap)
            cls._instance.STICKY_ZONE = {"x_min": 5, "x_max": 7, "y_min": 5, "y_max": 7}
            cls._instance.MAX_STUCK_COUNT = 2
            
            # Initialize C++ Collision Checker if available
            cls._instance._cpp_checker = None
            if USE_CPP_COLLISION:
                try:
                    cls._instance._cpp_checker = CollisionCheckerInterface()
                    cls._instance._cpp_checker.set_grid_size(cls._instance.GRID_SIZE, cls._instance.GRID_SIZE)
                    cls._instance._cpp_checker.set_sticky_zone(
                        cls._instance.STICKY_ZONE["x_min"],
                        cls._instance.STICKY_ZONE["x_max"],
                        cls._instance.STICKY_ZONE["y_min"],
                        cls._instance.STICKY_ZONE["y_max"]
                    )
                    print("[SIM] C++ CollisionChecker initialized")
                except Exception as e:
                    print(f"[SIM] Failed to init C++ CollisionChecker: {e}")
                    cls._instance._cpp_checker = None
            
        return cls._instance
    
    def is_in_sticky_zone(self, x: float, y: float) -> bool:
        """Check if coordinates are in the sticky zone (uses C++ if available)."""
        if self._cpp_checker:
            return self._cpp_checker.is_in_sticky_zone(x, y)
        return (self.STICKY_ZONE["x_min"] <= x <= self.STICKY_ZONE["x_max"] and 
                self.STICKY_ZONE["y_min"] <= y <= self.STICKY_ZONE["y_max"])

    
    def reset_positions(self, positions: Dict[str, List[int]] = None):
        """
        Reset robot positions to specific starting points.
        Critical for consistent evaluation scenarios.
        
        Args:
            positions (dict): Mapping of robot_id -> [x, y].
                              If None, resets to default (0,0) area.
        """
        default_positions = {
            "robot_1": [0, 0],
            "robot_2": [0, 1],
            "robot_3": [1, 0]
        }
        
        positions = positions or default_positions
        
        for robot_id, pos in positions.items():
            if robot_id in self.robot_states:
                self.robot_states[robot_id]["pose"] = list(pos)
                self.robot_states[robot_id]["target"] = list(pos)
                self.robot_states[robot_id]["status"] = "IDLE"
                self.robot_states[robot_id]["stuck_counter"] = 0
                self.robot_states[robot_id]["recovery_cooldown"] = 0
        
        print(f"[SIM] Reset positions to: {positions}")

    def tick(self, robot_id: str = None):
        """
        Advance the simulation state by one time step.
        Can update a specific robot or the entire fleet.
        """
        if robot_id:
            self._move_robot(robot_id)
        else:
            for rid in self.robot_states.keys():
                self._move_robot(rid)

    def _move_robot(self, robot_id: str):
        """
        Internal physics engine for a single robot.
        Handles movement, stuck logic, and cooldowns.
        Uses C++ collision checker when available for performance.
        """
        state = self.robot_states[robot_id]
        if state["status"] != "NAVIGATING":
            return

        # Handle recovery immunity (prevents getting stuck immediately after recovering)
        if state["recovery_cooldown"] > 0:
            state["recovery_cooldown"] -= 1

        # --- STUCK LOGIC (uses C++ CollisionChecker if available) ---
        is_in_zone = self.is_in_sticky_zone(state["pose"][0], state["pose"][1])

        if is_in_zone and state["recovery_cooldown"] == 0:
            state["stuck_counter"] += 1
            if state["stuck_counter"] >= self.MAX_STUCK_COUNT:
                state["status"] = "STUCK"
                return
        else:
            state["stuck_counter"] = 0

        # --- NAVIGATION LOGIC (Manhattan Movement) ---
        target = state["target"]
        pose = state["pose"]
        
        # Move one step towards target per tick
        if pose[0] < target[0]: 
            pose[0] += 1
        elif pose[0] > target[0]: 
            pose[0] -= 1
        elif pose[1] < target[1]:
            pose[1] += 1
        elif pose[1] > target[1]: 
            pose[1] -= 1
        
        # Check arrival
        if pose == target:
            state["status"] = "IDLE"

    def check_path_conflict(self, robot_id: str, target: List[int]) -> bool:
        """
        Detect if a target coordinate is occupied or claimed by another robot.
        """
        for other_id, other_state in self.robot_states.items():
            if other_id == robot_id:
                continue
            
            # Conflict 1: Another robot is heading to the same target
            if (other_state["target"] == target and 
                other_state["status"] == "NAVIGATING"):
                return True
            
            # Conflict 2: Another robot is already sitting at the target
            if other_state["pose"] == target:
                return True
        
        return False

    def get_all_robot_paths(self) -> Dict[str, Dict[str, Any]]:
        """Return a snapshot of the entire fleet state."""
        paths = {}
        for robot_id, state in self.robot_states.items():
            paths[robot_id] = {
                "current": state["pose"],
                "target": state["target"],
                "status": state["status"]
            }
        return paths

    def render(self, ax=None, show_grid=True, title="Warehouse Fleet Status"):
        """
        Generate a matplotlib visualization of the current state.
        """
        if ax is None:
            fig, ax = plt.subplots(figsize=(8, 8))
        
        ax.clear()
        ax.set_xlim(-0.5, self.GRID_SIZE + 0.5)
        ax.set_ylim(-0.5, self.GRID_SIZE + 0.5)
        ax.set_aspect('equal')
        ax.set_title(title, fontsize=14, fontweight='bold')
        ax.set_xlabel('X Position', fontsize=12)
        ax.set_ylabel('Y Position', fontsize=12)
        
        if show_grid:
            ax.grid(True, alpha=0.3, linestyle='--')
        
        # Draw sticky zone
        sticky = patches.Rectangle(
            (self.STICKY_ZONE["x_min"], self.STICKY_ZONE["y_min"]),
            self.STICKY_ZONE["x_max"] - self.STICKY_ZONE["x_min"],
            self.STICKY_ZONE["y_max"] - self.STICKY_ZONE["y_min"],
            linewidth=2, edgecolor='red', facecolor='orange', alpha=0.3,
            label='Sticky Zone'
        )
        ax.add_patch(sticky)
        
        # Draw robots
        colors = {"robot_1": "blue", "robot_2": "green", "robot_3": "purple"}
        markers = {"IDLE": "o", "NAVIGATING": "D", "STUCK": "X"}
        
        for robot_id, state in self.robot_states.items():
            pose = state["pose"]
            status = state["status"]
            color = colors.get(robot_id, "black")
            marker = markers.get(status, "o")
            
            # Robot Body
            ax.plot(pose[0], pose[1], marker=marker, markersize=20, 
                   color=color, label=f'{robot_id} ({status})',
                   markeredgewidth=2, markeredgecolor='black')
            
            # Navigation Arrow
            if status == "NAVIGATING":
                target = state["target"]
                ax.plot(target[0], target[1], 'x', markersize=15, 
                       color=color, markeredgewidth=3, alpha=0.6)
                ax.annotate('', xy=target, xytext=pose,
                          arrowprops=dict(arrowstyle='->', color=color, 
                                        lw=2, alpha=0.5))
        
        ax.legend(loc='upper left', fontsize=10)
        return ax


# ==============================================================================
# TOOL API IMPLEMENTATIONS
# Description: Concrete implementations of the abstract tool interfaces.
# ==============================================================================

class Navigator(BaseNavigator):
    def __init__(self, robot_id: str):
        super().__init__(robot_id)
        self.sim = WarehouseSim()

    def go_to_pose(self, x: float, y: float) -> Dict[str, Any]:
        target = [int(x), int(y)]
        self.sim.robot_states[self.robot_id]["target"] = target
        self.sim.robot_states[self.robot_id]["status"] = "NAVIGATING"
        self.sim.robot_states[self.robot_id]["stuck_counter"] = 0
        
        return {
            "status": "NAVIGATING", 
            "message": f"{self.robot_id} moving to ({x}, {y})"
        }


class Critic(BaseCritic):
    def __init__(self, robot_id: str):
        super().__init__(robot_id)
        self.sim = WarehouseSim()

    def get_status(self) -> Dict[str, Any]:
        current_state = self.sim.robot_states[self.robot_id]
        return {
            "state": current_state["status"],
            "pose": current_state["pose"],
            "target": current_state["target"]
        }


class Recovery(BaseRecovery):
    def __init__(self, robot_id: str):
        super().__init__(robot_id)
        self.sim = WarehouseSim()

    def execute_recovery(self, strategy: str) -> Dict[str, Any]:
        state = self.sim.robot_states[self.robot_id]
        
        if state["status"] != "STUCK":
            return {
                "status": "RECOVERY_FAILED", 
                "message": "Robot was not stuck."
            }

        current_x, current_y = state["pose"]
        sticky = self.sim.STICKY_ZONE
        
        # Simulated Recovery Logic (Teleports out of danger)
        if strategy == "reverse_and_turn_left":
            new_x = sticky["x_min"] - 1
            new_y = current_y
        elif strategy == "reverse_and_turn_right":
            new_x = sticky["x_max"] + 1
            new_y = current_y
        elif strategy == "forward_left":
            new_x = current_x
            new_y = sticky["y_min"] - 1
        elif strategy == "reverse_only":
            new_x = current_x
            new_y = sticky["y_max"] + 1
        else:
            # Fallback default
            new_x = sticky["x_max"] + 1
            new_y = current_y
        
        # Boundary checks
        new_x = max(0, min(self.sim.GRID_SIZE, new_x))
        new_y = max(0, min(self.sim.GRID_SIZE, new_y))
        
        # Apply effects
        state["pose"] = [new_x, new_y]
        state["recovery_cooldown"] = 10 # Grant immunity
        state["status"] = "IDLE"
        state["stuck_counter"] = 0
        
        return {
            "status": "RECOVERY_COMPLETE", 
            "message": f"Recovery '{strategy}' moved to [{new_x}, {new_y}]"
        }