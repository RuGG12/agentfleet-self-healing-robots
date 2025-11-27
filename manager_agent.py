#!/usr/bin/env python3
"""
manager_agent.py
Description: Defines the Fleet Manager Agent using Google ADK.
             Responsible for high-level task assignment, clearance granting,
             and monitoring fleet health.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import os

# --- ADK & Google Imports ---
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import FunctionTool
from google.genai import types

# --- Local Project Imports ---
from observability import obs
from manager_tools import (
    get_fleet_status,
    check_clearance,
    assign_task_to_robot,
    mark_task_complete,
    get_idle_robots,
    reallocate_failed_task
)

# --- Optimization Notes ---
# 1. Clearance Logic Fix: The system instruction now explicitly forces the agent 
#    to call 'check_clearance' before making any decisions, preventing hallucinations 
#    where the LLM would arbitrarily deny requests.
# 2. Token Efficiency: Instructions added to suppress chatty output.
# --------------------------

# Retry configuration for robust API calls
retry_config = types.HttpRetryOptions(
    attempts=5,
    exp_base=2,
    initial_delay=5,
    http_status_codes=[429, 500, 503, 504],
)


async def auto_save_to_memory(callback_context: CallbackContext):
    """
    Callback to automatically save the session state to long-term memory 
    after each agent turn.
    """
    try:
        invocation_context = callback_context._invocation_context
        session = invocation_context.session
        memory_service = invocation_context.memory_service
        
        if session and memory_service:
            await memory_service.add_session_to_memory(session)
            print(f"[Memory] ✓ Saved session {session.id[:8]}... to long-term memory")
    except Exception as e:
        print(f"[Memory] ✗ Error saving to memory: {e}")


def create_manager_agent():
    """
    Factory function to create the Fleet Manager Agent.
    Includes strict instructions for tool usage to ensure deterministic behavior.
    """
    
    tools = [
        FunctionTool(get_fleet_status),
        FunctionTool(check_clearance),
        FunctionTool(assign_task_to_robot),
        FunctionTool(mark_task_complete),
        FunctionTool(get_idle_robots),
        FunctionTool(reallocate_failed_task)
    ]
    
    manager_instruction = """You are the Fleet Manager for a warehouse robot fleet.

    When a worker requests clearance (e.g., "robot_1 is requesting clearance to navigate to (7, 9)"):

    Step 1 - ALWAYS call check_clearance(robot_id, target_x, target_y)

    Step 2 - Read the result carefully:
      - If result["clearance"] == "GRANTED":
        → Respond: "Clearance granted for robot_X to navigate to (X, Y). You may proceed."
      
      - If result["clearance"] == "DENIED":
        → Respond: "Clearance DENIED for robot_X. Reason: [explain]. Please wait."

    IMPORTANT: 
    - Do NOT make your own judgment about conflicts
    - TRUST the check_clearance() tool result
    - NEVER grant clearance without calling the tool first
    - NEVER deny clearance if the tool says "GRANTED"

    EXAMPLE CORRECT WORKFLOW:
    User: "robot_1 is requesting clearance to navigate to (7, 9)"
    You: [Call check_clearance("robot_1", 7, 9)]
    Tool returns: {"clearance": "GRANTED", "reason": "No conflicts detected"}
    You: "Clearance granted for robot_1 to navigate to (7, 9). You may proceed."

    OTHER RESPONSIBILITIES:

    1. TASK ASSIGNMENT
       When user requests deliveries:
       - Call get_idle_robots() to see available robots
       - Call assign_task_to_robot(robot_id, x, y) for each task
       - Confirm assignments clearly

    2. STATUS MONITORING
       - When worker reports "completed task to (x,y)": Call mark_task_complete(robot_id, success=True)
       - When worker reports "failed task": Call mark_task_complete(robot_id, success=False)

    3. FAILURE RECOVERY
       If a worker fails after 10 recovery attempts:
       - Call reallocate_failed_task(failed_robot_id)
       - Assign returned task to new robot

    4. MEMORY LOGGING
       When worker reports recovery details:
       - You must acknowledge briefly and ONCE.
       - STRICTLY FORBIDDEN: Do not repeat the acknowledgment for the same event.
       - If multiple reports come in, summarize: "Noted: Recovery successful for all robots."

    RULES:
    - ALWAYS call check_clearance() before granting/denying
    - NEVER override the tool's decision
    - Be concise and action-oriented
    - Use exact coordinates
    - DO NOT repeat sentences or get into output loops.
    
    CRITICAL: REDUCE CHAT
    - If you call a tool (like assign_task or check_clearance), JUST OUTPUT THE TOOL CALL.
    - Do not add "Okay, I will check..." or "Task assigned."
    - Silence is golden to save API tokens.
    """
    
    manager = LlmAgent(
        name="fleet_manager",
        model=Gemini(model="gemini-2.5-flash-lite", retry_options=retry_config),
        after_agent_callback=auto_save_to_memory,
        instruction=manager_instruction,
        tools=tools
    )
    
    return manager