#!/usr/bin/env python3
"""
tool_api.py
Description: Abstract Base Classes (Interfaces) for Robot Tools.
             Defines the strict contract that both the Simulation backend 
             and the ROS 2 backend must adhere to.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List

# --- Optimization Notes ---
# 1. Architecture: This file enforces the Dependency Inversion Principle. 
#    The high-level Agents (Manager/Workers) depend on these abstractions, 
#    not on concrete details. This allows seamless switching between 
#    'sim_tools.py' (Python Sim) and 'ros_tools.py' (Real/Gazebo Robots).
# --------------------------

class BaseNavigator(ABC):
    """
    Abstract interface for a robot's navigation capability.
    """
    def __init__(self, robot_id: str):
        self.robot_id = robot_id

    @abstractmethod
    def go_to_pose(self, x: float, y: float) -> Dict[str, Any]:
        """
        Command the robot to navigate to a specific (x, y) pose.
        Must be non-blocking (returns immediately after setting target).
        
        Args:
            x (float): Target X coordinate.
            y (float): Target Y coordinate.
            
        Returns:
            Dict[str, Any]: Status dictionary (e.g., {"status": "NAVIGATING"}).
        """
        pass


class BaseCritic(ABC):
    """
    Abstract interface for a robot's self-monitoring capability.
    """
    def __init__(self, robot_id: str):
        self.robot_id = robot_id

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Retrieve the robot's current operational state and position.
        
        Returns:
            Dict[str, Any]: Must contain keys:
                            - 'state': "IDLE", "NAVIGATING", "STUCK"
                            - 'pose': [x, y]
        """
        pass


class BaseRecovery(ABC):
    """
    Abstract interface for a robot's physical recovery capability.
    """
    def __init__(self, robot_id: str):
        self.robot_id = robot_id

    @abstractmethod
    def execute_recovery(self, strategy: str) -> Dict[str, Any]:
        """
        Execute a specific, named open-loop maneuver to unstuck the robot.
        
        Args:
            strategy (str): The name of the move (e.g., "reverse_and_turn_left").
        
        Returns:
            Dict[str, Any]: Outcome of the maneuver 
                            (e.g., {"status": "RECOVERY_COMPLETE"}).
        """
        pass