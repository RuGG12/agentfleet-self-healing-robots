#!/usr/bin/env python3
"""
recovery_database.py
Description: Persistent Recovery Learning Database.
             A simple JSON-based database that persists recovery experiences 
             across all sessions, enabling Long-Term Memory (LTM).

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path


class RecoveryDatabase:
    """Singleton database for recovery experiences."""
    
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
        """Load database from disk."""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r') as f:
                    data = json.load(f)
                    count = len(data.get('experiences', []))
                    print(f"✓ [RecoveryDB] Loaded {count} past experiences")
                    return data
            except Exception as e:
                print(f"✗ [RecoveryDB] Error loading database: {e}")
                return {"experiences": []}
        else:
            print("ℹ️ [RecoveryDB] No existing database found, starting fresh")
            return {"experiences": []}
    
    def _save(self):
        """Save database to disk."""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            print(f"✗ [RecoveryDB] Error saving database: {e}")
    
    def add_experience(self, robot_id: str, x: int, y: int, strategy: str, success: bool):
        """Record a recovery experience."""
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
        print(f"  [RecoveryDB] Recorded: {robot_id} used '{strategy}' at ({x},{y}) → {status}")
    
    def query_location(self, robot_id: str, x: int, y: int) -> Dict[str, Any]:
        """Query recovery history for a specific location."""
        if "experiences" not in self.data:
            return {
                "found": False,
                "experiences": [],
                "message": "No recovery history available"
            }
        
        # Find all experiences at this location
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
        
        # Separate successes and failures
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
        """Get list of strategies that worked at this location."""
        result = self.query_location(robot_id, x, y)
        return [exp["strategy"] for exp in result.get("successes", [])]
    
    def get_failed_strategies(self, robot_id: str, x: int, y: int) -> List[str]:
        """Get list of strategies that failed at this location."""
        result = self.query_location(robot_id, x, y)
        return [exp["strategy"] for exp in result.get("failures", [])]
    
    def clear(self):
        """Clear all history (for testing)."""
        self.data = {"experiences": []}
        self._save()
        print("✓ [RecoveryDB] Database cleared")


# Singleton instance
_db = RecoveryDatabase()


# =========================================================
# PUBLIC API (Used by Agents)
# =========================================================

def save_recovery_to_db(robot_id: str, x: int, y: int, strategy: str, success: bool) -> Dict[str, Any]:
    """Public API: Save a recovery experience to persistent database."""
    _db.add_experience(robot_id, x, y, strategy, success)
    return {
        "status": "saved",
        "message": f"Recorded '{strategy}' ({'success' if success else 'failed'}) at ({x},{y})"
    }


def query_recovery_from_db(robot_id: str, x: int, y: int) -> Dict[str, Any]:
    """Public API: Query recovery history from persistent database."""
    return _db.query_location(robot_id, x, y)


def get_recommended_strategy(robot_id: str, x: int, y: int, target_x: int, target_y: int) -> str:
    """
    Smart strategy recommendation based on history and target direction.
    """
    # Check history first
    successes = _db.get_successful_strategies(robot_id, x, y)
    failures = _db.get_failed_strategies(robot_id, x, y)
    
    # If we have a successful strategy, use it!
    if successes:
        return successes[0]  # Use the first successful one
    
    # Otherwise, pick based on target direction, avoiding failures
    available_strategies = [
        'reverse_and_turn_right',
        'reverse_and_turn_left',
        'forward_left',
        'reverse_only'
    ]
    
    # Remove failed strategies from consideration
    available = [s for s in available_strategies if s not in failures]
    
    if not available:
        # All strategies failed, try default anyway
        return 'reverse_and_turn_right'
    
    # Pick based on target direction
    dx = target_x - x
    dy = target_y - y
    
    if dy > 0:  # Target is north
        if 'reverse_only' in available:
            return 'reverse_only'
    
    if dx > 0:  # Target is east
        if 'reverse_and_turn_right' in available:
            return 'reverse_and_turn_right'
    
    if dx < 0:  # Target is west
        if 'reverse_and_turn_left' in available:
            return 'reverse_and_turn_left'
    
    # Default to first available
    return available[0]
