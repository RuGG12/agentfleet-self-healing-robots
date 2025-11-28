#!/usr/bin/env python3
"""
fleet_orchestrator.py
Description: Main entry point for the Multi-Agent Warehouse System.
             Orchestrates the Manager Agent and Worker Fleet, handles
             simulation ticking, and manages error recovery.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import asyncio
import os
import re
import uuid
import random

# --- Third Party Imports ---
import matplotlib.pyplot as plt
from google.genai import types

# --- ADK & Google Imports ---
from google.adk.agents import LlmAgent
from google.adk.apps.app import App
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.memory import InMemoryMemoryService

# --- Local Project Imports ---
# Observability
from observability import obs

# Agents & Logic
from manager_agent import create_manager_agent
from worker_agent import create_worker_agent, WorkerState
from manager_tools import reset_task_state, check_clearance
from recovery_database import save_recovery_to_db

# Simulation wrappers
from tool_wrappers import (
    tick_simulation,
    check_status_robot_1,
    check_status_robot_2,
    check_status_robot_3
)
from sim_tools import WarehouseSim


# --- Configuration & Setup ---
DB_URL = "sqlite:///agent_fleet.db"
session_service = DatabaseSessionService(db_url=DB_URL)
memory_service = InMemoryMemoryService()

MANAGER_APP_NAME = "manager_app"
WORKER_APP_NAME_PREFIX = "worker_app_"
USER_ID = "orchestrator"

# Handle API Key
try:
    from kaggle_secrets import UserSecretsClient
    GOOGLE_API_KEY = UserSecretsClient().get_secret("GOOGLE_API_KEY")
    os.environ["GOOGLE_API_KEY"] = GOOGLE_API_KEY
    print("✓ API key loaded from Kaggle secrets")
except ImportError:
    if "GOOGLE_API_KEY" not in os.environ:
        print("\n" + "=" * 70)
        print("⚠️ ERROR: GOOGLE_API_KEY not found!")
        print("=" * 70)
        exit(1)
    print("✓ API key loaded from environment")


def extract_strategy_from_response(response_text: str) -> str:
    """
    Parses the LLM response to identify the chosen recovery strategy.
    Uses strict regex matching first, falling back to fuzzy matching for robustness.
    """
    text = response_text.lower()

    # PHASE 1: Strict template match
    template_patterns = [
        r"using\s+strategy\s*[:=]\s*['\"]?([^'\"\n]+?)['\"]?",
        r"strategy\s*[:=]\s*['\"]?([^'\"\n]+?)['\"]?",
        r"i\s+will\s+use\s+['\"]?([^'\"\n]+?)['\"]?",
        r"chosen\s+strategy\s*[:=]\s*['\"]?([^'\"\n]+?)['\"]?",
    ]

    for pattern in template_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            if "reverse" in candidate and "left" in candidate:
                return "reverse_and_turn_left"
            if "reverse" in candidate and "right" in candidate:
                return "reverse_and_turn_right"
            if "reverse" in candidate and "only" in candidate:
                return "reverse_only"
            if "forward" in candidate and "left" in candidate:
                return "forward_left"

    # PHASE 2: Fuzzy fallback
    if any(phrase in text for phrase in ["reverse_only", "reverse only"]):
        return "reverse_only"
    if any(phrase in text for phrase in ["reverse_and_turn_left", "reverse and turn left", "turn left"]):
        return "reverse_and_turn_left"
    if any(phrase in text for phrase in ["reverse_and_turn_right", "reverse and turn right", "turn right"]):
        return "reverse_and_turn_right"
    if "forward_left" in text or "forward left" in text:
        return "forward_left"

    return "reverse_only"  # Safe default


class FleetOrchestrator:
    """
    Central controller for the robot fleet.
    Manages the lifecycle of the simulation, agent communication, and recovery logic.
    """

    def __init__(self):
        print("\n" + "=" * 70)
        print("INITIALIZING FLEET ORCHESTRATOR")
        print("=" * 70)

        # 1. Initialize Agents
        self.manager_agent = create_manager_agent()
        self.worker_agents = {
            "robot_1": create_worker_agent("robot_1"),
            "robot_2": create_worker_agent("robot_2"),
            "robot_3": create_worker_agent("robot_3")
        }
        print("✓ Created 4 agents (1 Manager + 3 Workers)")

        # 2. Initialize ADK Apps
        self.manager_app = App(name=MANAGER_APP_NAME, root_agent=self.manager_agent)
        self.worker_apps = {
            robot_id: App(name=f"{WORKER_APP_NAME_PREFIX}{robot_id}", root_agent=worker)
            for robot_id, worker in self.worker_agents.items()
        }
        print("✓ Created 4 ADK Apps")

        # 3. Initialize Runners
        self.manager_runner = Runner(
            app=self.manager_app,
            session_service=session_service,
            memory_service=memory_service
        )
        self.worker_runners = {
            robot_id: Runner(app=app, session_service=session_service, memory_service=memory_service)
            for robot_id, app in self.worker_apps.items()
        }
        print(f"✓ Created Runners with DB: {DB_URL}")

        # 4. State Management
        self.worker_states = {
            robot_id: WorkerState(robot_id)
            for robot_id in self.worker_agents.keys()
        }
        
        # 5. Simulation & Stats
        self.sim = WarehouseSim()
        reset_task_state()

        self.recovery_stats = {
            robot_id: {"attempts": 0, "successes": 0, "strategies_used": []}
            for robot_id in self.worker_agents.keys()
        }

        print("✓ Initialization complete")
        print("=" * 70 + "\n")

    async def _get_or_create_session(self, app_name: str, session_id: str):
        """Ensures a valid database session exists before processing."""
        try:
            await session_service.create_session(
                app_name=app_name,
                user_id=USER_ID,
                session_id=session_id
            )
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f" ⚠️ Session creation warning: {e}")

        return await session_service.get_session(
            app_name=app_name,
            user_id=USER_ID,
            session_id=session_id
        )

    async def send_to_manager(self, session_id: str, message: str, verbose: bool = True) -> str:
        """Helper to send messages to the Manager Agent."""
        if verbose:
            print(f"\n{'=' * 70}")
            print(f"USER → MANAGER (Session: {session_id[:12]}...)")
            print(f"Message: {message}")
            print(f"{'=' * 70}")

        await self._get_or_create_session(MANAGER_APP_NAME, session_id)

        response_text = ""
        query = types.Content(role="user", parts=[types.Part(text=message)])

        try:
            async for event in self.manager_runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=query
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
                            if verbose:
                                print(f"MANAGER: {part.text}")
        except Exception as e:
            print(f"✗ Manager error: {e}")
            response_text = f"ERROR: {e}"

        return response_text

    async def send_to_worker(self, robot_id: str, session_id: str, message: str, verbose: bool = True) -> str:
        """Helper to send messages to a specific Worker Agent."""
        if verbose:
            print(f"\n--- ORCHESTRATOR → {robot_id.upper()} (Session: {session_id[:12]}...)")
            print(f" Message: {message}")

        app_name = self.worker_apps[robot_id].name
        await self._get_or_create_session(app_name, session_id)

        response_text = ""
        query = types.Content(role="user", parts=[types.Part(text=message)])

        try:
            runner = self.worker_runners[robot_id]
            async for event in runner.run_async(
                user_id=USER_ID,
                session_id=session_id,
                new_message=query
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response_text += part.text
                            if verbose:
                                print(f" {robot_id.upper()}: {part.text}")
        except Exception as e:
            print(f" ✗ Worker error: {e}")
            response_text = f"ERROR: {e}"

        return response_text

    async def worker_execution_loop(self, robot_id: str, target_x: int, target_y: int,
                                    manager_session_id: str, max_ticks: int = 200):
        """
        Main execution loop for a single worker robot.
        Handles clearance, navigation, state monitoring, and recovery.
        """
        worker_state = self.worker_states[robot_id]
        worker_state.assign_task(target_x, target_y)
        worker_session_id = f"{robot_id}_task_{uuid.uuid4().hex[:6]}"

        print(f"\n{'=' * 70}")
        print(f"TASK START: {robot_id} → ({target_x}, {target_y})")
        print(f" Manager Session: {manager_session_id[:12]}...")
        print(f" Worker Session: {worker_session_id}")
        print(f"{'=' * 70}")

        # =========================================================
        # PHASE 1: CLEARANCE CHECK
        # =========================================================
        
        max_clearance_retries = 10
        clearance_granted = False

        obs.start_trace()
        obs.log_event("Orchestrator", "Task_Started",
                      metadata={"robot_id": robot_id, "target": [target_x, target_y]})

        for retry in range(max_clearance_retries):
            print(f"[{robot_id}] Requesting clearance (attempt {retry + 1}/{max_clearance_retries})...")

            clearance_result = check_clearance(robot_id, target_x, target_y)

            if clearance_result["clearance"] == "GRANTED":
                worker_state.grant_clearance()
                clearance_granted = True
                print(f"✓ Clearance GRANTED for {robot_id} (Direct)")
                break

            print(f"⚠️ Clearance attempt {retry + 1}/{max_clearance_retries} "
                  f"DENIED for {robot_id}: {clearance_result['reason']}")

            # Staggered-start logic to prevent API congestion
            try:
                r_num = int(robot_id.split('_')[-1])
                start_delay = (r_num - 1) * 20
                if start_delay > 0:
                    print(f"⏳ [Orchestrator] {robot_id} enforcing {start_delay}s start delay...")
                    await asyncio.sleep(start_delay)
            except:
                pass

            wait_time = min(15.0, 0.5 * (2 ** retry))
            await asyncio.sleep(wait_time)

        if not clearance_granted:
            print(f"✗ Clearance DENIED for {robot_id} after {max_clearance_retries} attempts")
            worker_state.mark_complete(success=False)
            return False

        # =========================================================
        # PHASE 2: NAVIGATION COMMAND
        # =========================================================
        nav_msg = f"Navigate {robot_id} to coordinates ({target_x}, {target_y})"
        await self.send_to_worker(robot_id, worker_session_id, nav_msg)

        # =========================================================
        # PHASE 3: EXECUTION MONITORING
        # =========================================================
        tick_count = 0
        
        # Select status function based on ID
        status_funcs = {
            "robot_1": check_status_robot_1,
            "robot_2": check_status_robot_2,
            "robot_3": check_status_robot_3
        }
        check_status = status_funcs[robot_id]

        recovery_history = []
        last_position = None
        idle_counter = 0

        while tick_count < max_ticks:
            tick_count += 1
            tick_simulation()

            status = check_status()
            robot_status = status['state']
            robot_pose = status['pose']

            if tick_count % 5 == 0:
                print(f" [Tick {tick_count}] {robot_id} at {robot_pose} - {robot_status}")

            # --- Handling IDLE State ---
            if robot_status == "IDLE":
                if robot_pose == [target_x, target_y]:
                    # SUCCESS: Robot reached target
                    obs.log_event("Orchestrator", "Task_Completed",
                                  metadata={"duration_ticks": tick_count})
                    print(f"\n✓ {robot_id} REACHED TARGET ({target_x}, {target_y}) in {tick_count} ticks")

                    # Log recovery stats if any happened
                    stats = self.recovery_stats[robot_id]
                    if recovery_history:
                        obs.log_event("Orchestrator", "Recovery_Success",
                                      metadata={"count": len(recovery_history)})
                        stats["successes"] += len(recovery_history)
                        print(f" 📊 Recovery Stats: {len(recovery_history)} recoveries succeeded")
                        for rec in recovery_history:
                            save_recovery_to_db(
                                robot_id, rec['location'][0], rec['location'][1],
                                rec['strategy'], success=True
                            )

                    worker_state.mark_complete(success=True)

                    success_msg = f"{robot_id} successfully completed its task to ({target_x}, {target_y})."
                    if recovery_history:
                        strategies = ", ".join([r['strategy'] for r in recovery_history])
                        success_msg += f" Used {len(recovery_history)} recoveries: {strategies}."

                    await self.send_to_manager(manager_session_id, success_msg)
                    return True

                # IDLE BUT NOT AT TARGET (Fix Implementation)
                # Optimization: Aggressive re-instruction logic.
                # BEFORE: Robot might idle indefinitely if it missed a command.
                # NOW: Detects position shifts or persistent idling and force a "WAKE UP" command.
                if last_position != robot_pose:
                    idle_counter = 0
                    last_position = robot_pose
                    print(f" [Orchestrator] ℹ️ {robot_id} moved to {robot_pose}. Re-issuing nav command.")
                    nav_msg = (
                        f"You are currently at {robot_pose}. Resume navigation IMMEDIATELY "
                        f"to ({target_x}, {target_y})."
                    )
                    await self.send_to_worker(robot_id, worker_session_id, nav_msg, verbose=True)
                else:
                    idle_counter += 1
                    if idle_counter >= 3:
                        print(f" [Orchestrator] ⚠️ {robot_id} is idling at {robot_pose}. Forcing movement.")
                        nav_msg = (
                            f"WAKE UP. You are IDLE at {robot_pose}. You MUST call navigate_{robot_id} "
                            f"to ({target_x}, {target_y}) NOW."
                        )
                        await self.send_to_worker(robot_id, worker_session_id, nav_msg, verbose=True)
                        idle_counter = 0

            # --- Handling STUCK State ---
            elif robot_status == "STUCK":
                is_critical = worker_state.increment_recovery()
                obs.log_event("Orchestrator", "Recovery_Triggered", "WARN",
                              metadata={"location": robot_pose})

                if is_critical:
                    print(f"\n{robot_id} CRITICAL FAILURE — triggering reallocation")
                    worker_state.mark_complete(success=False)

                    if recovery_history:
                        for rec in recovery_history:
                            save_recovery_to_db(
                                robot_id=robot_id, x=rec['location'][0], y=rec['location'][1],
                                strategy=rec['strategy'], success=False
                            )

                    realloc_msg = f"Reallocate the failed task for {robot_id} to ({target_x}, {target_y})"
                    failure_msg = f"{robot_id} has failed its task after 3 recovery attempts at {robot_pose}."

                    await self.send_to_manager(manager_session_id, realloc_msg)
                    await self.send_to_manager(manager_session_id, failure_msg)
                    return True

                print(f"\nWarning: {robot_id} STUCK at {robot_pose} (attempt #{worker_state.recovery_attempts})")
                self.recovery_stats[robot_id]["attempts"] += 1

                recovery_msg = (
                    f"{robot_id} is STUCK at {robot_pose}. Target is ({target_x}, {target_y}). "
                    f"Execute adaptive recovery."
                )
                recovery_response = await self.send_to_worker(robot_id, worker_session_id, recovery_msg)

                strategy_used = extract_strategy_from_response(recovery_response)

                recovery_history.append({
                    "location": list(robot_pose),
                    "strategy": strategy_used,
                    "attempt": worker_state.recovery_attempts
                })

                self.recovery_stats[robot_id]["strategies_used"].append(strategy_used)
                print(f" Executed recovery: {strategy_used}")

                last_position = None
                idle_counter = 0
                await asyncio.sleep(0.5)

            await asyncio.sleep(0.1)

        print(f"\n⏱️ {robot_id} TIMEOUT after {max_ticks} ticks")
        worker_state.mark_complete(success=False)
        return False


async def main():
    """Run the evaluation scenario."""
    print("\n" + "=" * 70)
    print("AGENTFLEET EVALUATION")
    print("=" * 70)

    orchestrator = FleetOrchestrator()
    manager_session_id = f"trial_fixed_{uuid.uuid4().hex[:8]}"

    print("\n📦 Test delivery: All robots to (7,9), (6,9), (5,9)")
    await orchestrator.send_to_manager(
        manager_session_id,
        "Deliver to: robot_1 to (7,9), robot_2 to (6,9), robot_3 to (5,9). Assign tasks."
    )

    # Launch concurrent tasks
    task1 = orchestrator.worker_execution_loop("robot_1", 7, 9, manager_session_id, max_ticks=120)
    task2 = orchestrator.worker_execution_loop("robot_2", 6, 9, manager_session_id, max_ticks=120)
    task3 = orchestrator.worker_execution_loop("robot_3", 5, 9, manager_session_id, max_ticks=120)

    results = await asyncio.gather(task1, task2, task3)

    print("\n" + "=" * 70)
    print("TEST RESULTS")
    print("=" * 70)

    success_count = sum(results)
    print(f"\nTasks completed: {success_count}/3")

    for robot_id in ["robot_1", "robot_2", "robot_3"]:
        stats = orchestrator.recovery_stats[robot_id]
        print(f"\n{robot_id}:")
        print(f" Attempts: {stats['attempts']}")
        print(f" Successes: {stats['successes']}")
        if stats['strategies_used']:
            print(f" Strategies: {', '.join(stats['strategies_used'])}")

    print("\n" + "=" * 70)


if __name__ == "__main__":

    asyncio.run(main())


