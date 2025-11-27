#!/usr/bin/env python3
"""
tool_api.py
Description: Abstract Base Classes (Contract) for Robot Tools.
             Ensures consistent interface between Simulation and ROS implementations.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseNavigator(ABC):
    """Abstract interface for a robot's navigation tool."""
    def __init__(self, robot_id: str):
        self.robot_id = robot_id

    @abstractmethod
    def go_to_pose(self, x: float, y: float) -> Dict[str, Any]:
        """
        Commands the robot to navigate to a specific (x, y) pose.
        This function should be non-blocking (it returns immediately).
        
        Returns:
            Dict[str, Any]: A dictionary confirming the command was accepted.
                            e.g., {"status": "NAVIGATING", "message": "Task received."}
        """
        pass

class BaseCritic(ABC):
    """Abstract interface for a robot's status-checking tool."""
    def __init__(self, robot_id: str):
        self.robot_id = robot_id

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        Gets the robot's current state and pose.
        
        Returns:
            Dict[str, Any]: A dictionary with the robot's state and pose.
                            e.g., {"state": "MOVING", "pose": [x, y]}
                            e.g., {"state": "STUCK", "pose": [x, y]}
                            e.g., {"state": "IDLE", "pose": [x, y]}
        """
        pass

class BaseRecovery(ABC):
    """Abstract interface for a robot's recovery-maneuver tool."""
    def __init__(self, robot_id: str):
        self.robot_id = robot_id

    @abstractmethod
    def execute_recovery(self, strategy: str) -> Dict[str, Any]:
        """
        Executes a specific, named recovery maneuver.
        
        Args:
            strategy (str): The name of the recovery move 
                            (e.g., "reverse_and_turn_left").
        
        Returns:
            Dict[str, Any]: A dictionary confirming the recovery is complete.
                            e.g., {"status": "RECOVERY_COMPLETE", "message": "..."}
                            e.g., {"status": "RECOVERY_FAILED", "message": "..."}
        """
        pass
