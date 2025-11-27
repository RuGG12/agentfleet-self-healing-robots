#!/usr/bin/env python3
"""
worker_agent.py
Description: Worker Agent definition with improved recovery strategy logic.
             Handles local navigation, status checks, and adaptive recovery.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import os
import json
import random
from typing import Dict, Any

# --- Third Party Imports ---
from google.genai import types

# --- ADK & Google Imports ---
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import FunctionTool, load_memory
from google.adk.tools.tool_context import ToolContext

# --- Local Project Imports ---
from tool_wrappers import get_robot_tools
from recovery_database import (
    save_recovery_to_db, 
    query_recovery_from_db, 
    get_recommended_strategy
)

retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=2,
    initial_delay=5,
    http_status_codes=[429, 500, 503, 504],
)


class WorkerState:
    """Tracks worker state (used by orchestrator)."""
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
        """Increment recovery count. Return True if critical."""
        self.recovery_attempts += 1
        return self.recovery_attempts >= 3

    def mark_complete(self, success: bool):
        self.task_active = False
        self.target = [0, 0]
        self.has_clearance = False
        self.recovery_attempts = 0


def save_recovery_experience(
    tool_context: ToolContext,
    robot_id: str,
    x: int,
    y: int,
    strategy: str,
    success: bool
) -> Dict[str, Any]:
    """Save a recovery experience to persistent database."""
    return save_recovery_to_db(robot_id, x, y, strategy, success)


def query_recovery_history(
    tool_context: ToolContext,
    robot_id: str,
    x: int,
    y: int
) -> Dict[str, Any]:
    """Query past recovery attempts at this location."""
    return query_recovery_from_db(robot_id, x, y)


def recommend_strategy(
    tool_context: ToolContext,
    robot_id: str,
    stuck_x: int,
    stuck_y: int,
    target_x: int,
    target_y: int
) -> Dict[str, Any]:
    """Get AI-recommended strategy based on history and target direction."""
    
    # 1. Check what failed previously using PUBLIC API
    history = query_recovery_from_db(robot_id, stuck_x, stuck_y)
    failures = [exp["strategy"] for exp in history.get("failures", [])]
    
    # 2. Get the algorithmic recommendation
    strategy = get_recommended_strategy(robot_id, stuck_x, stuck_y, target_x, target_y)
    
    # 3. Anti-Loop Logic: Randomize if primary choice is blocked
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
            # RANDOMIZE selection to prevent deterministic looping
            strategy = random.choice(viable)
            print(f"  [SmartSwitch] Randomly selected '{strategy}' to avoid past failures: {failures}")

    return {
        "recommended_strategy": strategy,
        "forbidden_strategies": failures, 
        "message": f"Recommended: '{strategy}'. History shows {len(failures)} failures to avoid."
    }


def create_worker_agent(robot_id: str):
    """Creates an ADK agent with IMPROVED recovery strategy selection."""
    
    nav_tool, status_tool, recovery_tool, memory_tool = get_robot_tools(robot_id)
    save_tool = FunctionTool(save_recovery_experience)
    query_tool = FunctionTool(query_recovery_history)
    recommend_tool = FunctionTool(recommend_strategy)
    
    agent = LlmAgent(
        name=f"{robot_id}_worker",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        
        instruction=f"""You are the autonomous navigation specialist for {robot_id}.

Your tools:
1. navigate_{robot_id}(x, y)
2. check_status_{robot_id}()
3. recover_{robot_id}(strategy)
4. recommend_strategy(...)
5. save_recovery_experience(...)

CRITICAL RULES FOR "WAKE UP" COMMANDS:
If the user says "WAKE UP" or "Resume navigation", you MUST call navigate_{robot_id} immediately.
- DO NOT argue that you are already navigating.
- DO NOT say "I will continue".
- JUST CALL THE TOOL.
- If you are idle, you must move.

NAVIGATION WORKFLOW:
1. Call navigate_{robot_id}(X, Y)
2. Respond: "Navigating {robot_id} to (X, Y)"

RECOVERY WORKFLOW (When told "STUCK"):
1. Call recommend_strategy(...)
2. Call recover_{robot_id}(recommended_strategy)
3. Call save_recovery_experience(...)
4. Explain: "Using strategy: 'STRATEGY_NAME'. Reason: ..."
""",
        tools=[nav_tool, status_tool, recovery_tool, memory_tool, save_tool, query_tool, recommend_tool]
    )
    
    return agent
