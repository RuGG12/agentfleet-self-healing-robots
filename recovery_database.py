#!/usr/bin/env python3
"""
recovery_database.py
Description: Persistent Long-Term Memory (LTM) for Robot Recovery.
             Maintains a JSON-based record of which recovery strategies worked 
             or failed at specific locations, allowing the fleet to "learn" 
             from past mistakes across different simulation sessions.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

# --- Optimization Notes ---
# 1. Singleton Pattern: Ensures a single point of truth for the database across 
#    all concurrent agent threads.
# 2. Adaptive Learning: The 'get_recommended_strategy' function implements 
#    reinforcement learning principles by permanently filtering out strategies 
#    that failed at specific coordinates.
# --------------------------

class RecoveryDatabase:
    """
    Singleton database manager for persisting recovery experiences.
    """
    
    _instance = None
    _db_file = "recovery_history.json"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RecoveryDatabase, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self.db_path = Path(self._db_file)
        self.data = self._load()
    
    def _load(self) -> Dict[str, Any]:
        """Load database from disk if it exists."""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    print(f"[RecoveryDB] Loaded {len(data.get('experiences', []))} past experiences")
                    return data
            except Exception as e:
                print(f"[RecoveryDB] Error loading database: {e}")
                return {"experiences": []}
        else:
            print("[RecoveryDB] No existing database found, starting fresh")
            return {"experiences": []}
    
    def _save(self):
        """Persist current state to disk."""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"[RecoveryDB] Error saving database: {e}")
    
    def add_experience(self, robot_id: str, x: int, y: int, strategy: str, success: bool):
        """
        Record a new recovery attempt.
        """
        experience = {
            "robot_id": robot_id,
            "location": [x, y],
            "strategy": strategy,
            "success": success
        }
        
        if "experiences" not in self.data:
            self.data["experiences"] = []
        
        self.data["experiences"].append(experience)
        self._save()
        
        status = "SUCCESS" if success else "FAILED"
        print(f"[RecoveryDB] Recorded: {robot_id} used '{strategy}' at ({x},{y}) → {status}")
    
    def query_location(self, robot_id: str, x: int, y: int) -> Dict[str, Any]:
        """
        Retrieve all history for a specific robot at specific coordinates.
        """
        if "experiences" not in self.data:
            return {
                "found": False,
                "experiences": [],
                "message": "No recovery history available"
            }
        
        # Filter for specific robot and location
        matches = [
            exp for exp in self.data["experiences"]
            if exp["robot_id"] == robot_id and exp["location"] == [x, y]
        ]
        
        if not matches:
            return {
                "found": False,
                "experiences": [],
                "message": f"No history for {robot_id} at ({x},{y})"
            }
        
        # Categorize results
        successes = [exp for exp in matches if exp["success"]]
        failures = [exp for exp in matches if not exp["success"]]
        
        return {
            "found": True,
            "experiences": matches,
            "successes": successes,
            "failures": failures,
            "message": f"Found {len(matches)} experiences: {len(successes)} successes, {len(failures)} failures"
        }
    
    def get_successful_strategies(self, robot_id: str, x: int, y: int) -> List[str]:
        """Helper to return only strategies that worked previously."""
        result = self.query_location(robot_id, x, y)
        return [exp["strategy"] for exp in result.get("successes", [])]
    
    def get_failed_strategies(self, robot_id: str, x: int, y: int) -> List[str]:
        """Helper to return strategies known to fail."""
        result = self.query_location(robot_id, x, y)
        return [exp["strategy"] for exp in result.get("failures", [])]
    
    def clear(self):
        """Wipe database (Use for testing/reset)."""
        self.data = {"experiences": []}
        self._save()
        print("[RecoveryDB] Database cleared")


# Initialize Singleton
_db = RecoveryDatabase()


# ==============================================================================
# PUBLIC API FUNCTIONS
# Description: Wrappers for external tools (ADK FunctionTools)
# ==============================================================================

def save_recovery_to_db(robot_id: str, x: int, y: int, strategy: str, success: bool) -> Dict[str, Any]:
    """
    Public API: Save a recovery experience to persistent database.
    
    Returns:
        Dict: Confirmation message.
    """
    _db.add_experience(robot_id, x, y, strategy, success)
    return {
        "status": "saved",
        "message": f"Recorded '{strategy}' ({'success' if success else 'failed'}) at ({x},{y})"
    }


def query_recovery_from_db(robot_id: str, x: int, y: int) -> Dict[str, Any]:
    """
    Public API: Query recovery history from persistent database.
    
    Returns:
        Dict: Full history object with successes/failures.
    """
    return _db.query_location(robot_id, x, y)


def get_recommended_strategy(robot_id: str, x: int, y: int, target_x: int, target_y: int) -> str:
    """
    Public API: Intelligent strategy recommendation engine.
    Prioritizes proven successes, avoids known failures, and uses heuristics 
    based on target direction for new scenarios.
    
    Args:
        robot_id (str): Robot identifier.
        x (int): Current X.
        y (int): Current Y.
        target_x (int): Destination X.
        target_y (int): Destination Y.
    
    Returns:
        str: The recommended strategy name.
    """
    # 1. Check Long-Term Memory first
    successes = _db.get_successful_strategies(robot_id, x, y)
    failures = _db.get_failed_strategies(robot_id, x, y)
    
    # If we have a proven winner, use it immediately
    if successes:
        return successes[0]
    
    # 2. Heuristic Calculation
    # If no history, pick based on target direction, but filter out known failures
    available_strategies = [
        'reverse_and_turn_right',
        'reverse_and_turn_left',
        'forward_left',
        'reverse_only'
    ]
    
    # Remove strategies that failed here in the past
    available = [s for s in available_strategies if s not in failures]
    
    if not available:
        # If everything failed previously, reset to a safe default
        return 'reverse_and_turn_right'
    
    # Calculate direction vector
    dx = target_x - x
    dy = target_y - y
    
    # Directional heuristics
    if dy > 0:  # Target is North
        if 'reverse_only' in available:
            return 'reverse_only'
    
    if dx > 0:  # Target is East
        if 'reverse_and_turn_right' in available:
            return 'reverse_and_turn_right'
    
    if dx < 0:  # Target is West
        if 'reverse_and_turn_left' in available:
            return 'reverse_and_turn_left'
    
    # Fallback: first available valid strategy
    return available[0]