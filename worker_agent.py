#!/usr/bin/env python3
"""
worker_agent.py
Description: Defines the Worker Agent (Robot) logic.
             Includes the "WorkerState" tracking class and the LLM Agent definition
             equipped with Navigation, Status, and Adaptive Recovery tools.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import os
import json
import random
from typing import Dict, Any

# --- ADK Imports ---
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool, load_memory
from google.adk.tools.tool_context import ToolContext
from google.genai import types

# --- Local Project Imports ---
from tool_wrappers import get_robot_tools
from recovery_database import (
    save_recovery_to_db, 
    query_recovery_from_db, 
    get_recommended_strategy
)

# --- Optimization Notes ---
# 1. Adaptive Strategy: The 'recommend_strategy' tool connects the LLM to the 
#    Long-Term Memory (LTM) database. It filters out strategies that failed 
#    at the specific location in the past.
# 2. Stochastic Fallback: Implemented 'SmartSwitch' logic. If the deterministic 
#    algorithm recommends a strategy that is known to fail (edge case), 
#    it forces a random selection from viable alternatives to break infinite loops.
# --------------------------

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=2,
    initial_delay=5,
    http_status_codes=[429, 500, 503, 504],
)


class WorkerState:
    """
    State container used by the Orchestrator to track task progress 
    and recovery attempts for a specific robot.
    """
    def __init__(self, robot_id: str):
        self.robot_id = robot_id
        self.target = [0, 0]
        self.has_clearance = False
        self.recovery_attempts = 0
        self.task_active = False

    def assign_task(self, x: int, y: int):
        self.target = [x, y]
        self.has_clearance = False
        self.recovery_attempts = 0
        self.task_active = True

    def grant_clearance(self):
        self.has_clearance = True

    def increment_recovery(self) -> bool:
        """
        Increments recovery counter. 
        Returns True if the retry limit (3) is reached (Critical Failure).
        """
        self.recovery_attempts += 1
        return self.recovery_attempts >= 3

    def mark_complete(self, success: bool):
        self.task_active = False
        self.target = [0, 0]
        self.has_clearance = False
        self.recovery_attempts = 0


# ==============================================================================
# AGENT TOOLS (ADAPTIVE RECOVERY)
# Description: Tools that interact with the persistent recovery database.
# ==============================================================================

def save_recovery_experience(
    tool_context: ToolContext,
    robot_id: str,
    x: int,
    y: int,
    strategy: str,
    success: bool
) -> Dict[str, Any]:
    """Wrapper to save recovery outcomes to the persistent DB."""
    return save_recovery_to_db(robot_id, x, y, strategy, success)


def query_recovery_history(
    tool_context: ToolContext,
    robot_id: str,
    x: int,
    y: int
) -> Dict[str, Any]:
    """Wrapper to query past recovery attempts."""
    return query_recovery_from_db(robot_id, x, y)


def recommend_strategy(
    tool_context: ToolContext,
    robot_id: str,
    stuck_x: int,
    stuck_y: int,
    target_x: int,
    target_y: int
) -> Dict[str, Any]:
    """
    Intelligent Strategy Recommender.
    Combines algorithmic direction heuristics with historical failure data.
    """
    
    # 1. Check history (What failed here before?)
    # Using public API to avoid direct DB access issues
    history = query_recovery_from_db(robot_id, stuck_x, stuck_y)
    failures = [exp["strategy"] for exp in history.get("failures", [])]
    
    # 2. Get algorithmic recommendation
    strategy = get_recommended_strategy(robot_id, stuck_x, stuck_y, target_x, target_y)
    
    # 3. Anti-Loop Logic (SmartSwitch)
    # If the algorithm recommends something that failed previously, randomize to break the loop.
    if strategy in failures:
        available = [
            'reverse_only',
            'reverse_and_turn_right',
            'reverse_and_turn_left',
            'forward_left'
        ]
        # Filter out known failures
        viable = [s for s in available if s not in failures]
        
        if viable:
            strategy = random.choice(viable)
            print(f"  [SmartSwitch] Randomly selected '{strategy}' to avoid past failures: {failures}")

    return {
        "recommended_strategy": strategy,
        "forbidden_strategies": failures, 
        "message": f"Recommended: '{strategy}'. History shows {len(failures)} failures to avoid."
    }


# ==============================================================================
# AGENT FACTORY
# ==============================================================================

def create_worker_agent(robot_id: str):
    """
    Factory function to create a Worker Agent instance.
    Configured with Gemini 2.5 Flash Lite and adaptive recovery tools.
    """
    
    # Get base robot tools (Navigation, Status, Recovery)
    nav_tool, status_tool, recovery_tool, memory_tool = get_robot_tools(robot_id)
    
    # Add LTM (Long-Term Memory) Tools
    save_tool = FunctionTool(save_recovery_experience)
    query_tool = FunctionTool(query_recovery_history)
    recommend_tool = FunctionTool(recommend_strategy)
    
    # Instructions emphasize the "Ask for Recommendation" workflow
    instruction_text = f"""You are the autonomous navigation specialist for {robot_id} with ADAPTIVE LEARNING.

    Your tools:
    1. navigate_{robot_id}(x, y) - Command robot to navigate
    2. check_status_{robot_id}() - Check robot state
    3. recover_{robot_id}(strategy) - Execute recovery maneuver
    4. load_memory() - Query long-term memory
    5. query_recovery_history(robot_id, x, y) - Check past attempts at this location
    6. save_recovery_experience(robot_id, x, y, strategy, success) - Record outcomes
    7. recommend_strategy(robot_id, stuck_x, stuck_y, target_x, target_y) - Get AI advice

    NAVIGATION WORKFLOW:
    When asked "Navigate {robot_id} to (X, Y)":
    1. Call navigate_{robot_id}(X, Y)
    2. Respond: "Navigating {robot_id} to (X, Y)"

    IMPROVED ADAPTIVE RECOVERY WORKFLOW:
    When told "{robot_id} is STUCK at [X, Y]. Target is (TX, TY)":

    Step 1 - GET RECOMMENDATION (CRITICAL):
      Call recommend_strategy("{robot_id}", X, Y, TX, TY)
      This tool analyzes history and direction to give you the BEST strategy.

    Step 2 - EXECUTE:
      Read the 'recommended_strategy' from the tool output.
      Call recover_{robot_id}(recommended_strategy)

    Step 3 - RECORD:
      Call save_recovery_experience("{robot_id}", X, Y, chosen_strategy, False)

    Step 4 - EXPLAIN (EXACT FORMAT REQUIRED):
      "Using strategy: 'STRATEGY_NAME'. Reason: YOUR_REASONING"
      
      VALID STRATEGY_NAMES:
      - reverse_and_turn_right
      - reverse_and_turn_left
      - forward_left
      - reverse_only

    RULES:
    - ALWAYS call recommend_strategy first
    - TRUST the recommendation (it avoids past failures)
    - Use the EXACT format for reporting strategy
    - Be decisive and clear
    """
    
    agent = LlmAgent(
        name=f"{robot_id}_worker",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        instruction=instruction_text,
        tools=[nav_tool, status_tool, recovery_tool, memory_tool, save_tool, query_tool, recommend_tool]
    )
    
    return agent