#!/usr/bin/env python3
"""
evaluate_fleet.py
Description: Enhanced Evaluation Framework for the Agent Fleet.
             Forces robots into guaranteed edge cases (Sticky Zones) to rigorously
             test the adaptive recovery and learning capabilities.
             Generates JSON reports and Matplotlib visualizations.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict

# --- Third Party Imports ---
import numpy as np
import matplotlib.pyplot as plt

# --- Local Project Imports ---
from fleet_orchestrator import FleetOrchestrator  
from sim_tools import WarehouseSim
from recovery_database import RecoveryDatabase
from observability import obs

# --- Optimization Notes ---
# 1. Forced Edge Cases: Instead of random testing, this script forces robots 
#    to cross "Sticky Zones" by manipulating start/end coordinates. This proves 
#    the agent's resilience is not just luck.
# 2. Automated Analytics: Generates professional charts (trend lines, success rates)
#    automatically, which is perfect for the "Presentation/Video" deliverables.
# --------------------------

@dataclass
class TrialResult:
    """Data structure for a single evaluation run."""
    trial_id: str
    scenario_name: str
    start_positions: Dict[str, List[int]]
    start_time: float
    end_time: float
    duration: float
    tasks_assigned: int
    tasks_completed: int
    tasks_failed: int
    success_rate: float
    total_recoveries: int
    recovery_success_rate: float
    strategies_used: Dict[str, int]
    robot_stats: Dict[str, Dict[str, Any]]


class EnhancedEvaluationFramework:
    """
    Manages the execution of rigorous test scenarios to benchmark fleet performance.
    """
    
    def __init__(self, output_dir: str = "evaluation_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[TrialResult] = []
    
    def define_test_scenarios(self) -> List[Dict[str, Any]]:
        """
        Define scenarios with STARTING POSITIONS that force sticky zone crossing.
        Key insight: Control where robots START, not just where they go.
        """
        return [
            {
                "name": "Scenario_1_North_Crossing",
                "start_positions": {
                    "robot_1": [7, 3],  # Must go through sticky to reach north
                    "robot_2": [6, 2],
                    "robot_3": [5, 3]
                },
                "tasks": {
                    "robot_1": (7, 9),
                    "robot_2": (6, 9),
                    "robot_3": (5, 9)
                },
                "description": "All start south, target north - guaranteed sticky crossing"
            },
            {
                "name": "Scenario_2_East_Crossing",
                "start_positions": {
                    "robot_1": [2, 7],
                    "robot_2": [3, 6],
                    "robot_3": [2, 5]
                },
                # Optimization: Staggered X targets prevent destination congestion
                "tasks": {
                    "robot_1": (9, 7),  # Long range
                    "robot_2": (5, 6),  # Short range
                    "robot_3": (7, 5)   # Medium range
                },
                "description": "All start west, target east - guaranteed sticky crossing"
            },
            {
                "name": "Scenario_3_Diagonal_NE",
                "start_positions": {
                    "robot_1": [3, 3],  # Diagonal through sticky
                    "robot_2": [2, 2],
                    "robot_3": [4, 3]
                },
                "tasks": {
                    "robot_1": (8, 8),
                    "robot_2": (9, 9),
                    "robot_3": (8, 9)
                },
                "description": "Southwest to northeast - diagonal sticky crossing"
            },
            {
                "name": "Scenario_4_Center_Targets",
                "start_positions": {
                    "robot_1": [6, 2],  # Start south of sticky, target inside
                    "robot_2": [7, 3],
                    "robot_3": [5, 2]
                },
                "tasks": {
                    "robot_1": (6, 6),  # Target IN center of sticky
                    "robot_2": (7, 6),
                    "robot_3": (5, 6)
                },
                "description": "Targets INSIDE sticky zone - maximum difficulty"
            },
            {
                "name": "Scenario_5_Mixed_Directions",
                "start_positions": {
                    "robot_1": [2, 6],  # West, going east
                    "robot_2": [6, 2],  # South, going north
                    "robot_3": [3, 3]   # Southwest, going northeast
                },
                "tasks": {
                    "robot_1": (9, 6),
                    "robot_2": (6, 9),
                    "robot_3": (8, 8)
                },
                "description": "Different directions, all through sticky"
            }
        ]
    
    async def run_single_trial(self, scenario: Dict[str, Any], trial_num: int, verbose: bool = False) -> TrialResult:
        """Run a single trial with controlled starting positions."""
        trial_id = f"{scenario['name']}_{trial_num}"
        
        print(f"\n{'='*70}")
        print(f"TRIAL {trial_num}: {scenario['name']}")
        print(f"Description: {scenario['description']}")
        print(f"Start positions: {scenario['start_positions']}")
        print(f"{'='*70}")
        
        # 1. Reset Simulation to specific scenario start
        sim = WarehouseSim()
        sim.reset_positions(scenario['start_positions'])
        
        # 2. Initialize Orchestrator
        orchestrator = FleetOrchestrator()
        start_time = time.time()
        
        tasks = scenario['tasks']
        manager_session_id = f"eval_{trial_id}"
        
        # 3. Send Task Batch to Manager
        task_msg = ", ".join([f"{robot} to {target}" for robot, target in tasks.items()])
        await orchestrator.send_to_manager(
            manager_session_id,
            f"Deliver to: {task_msg}. Assign tasks.",
            verbose=verbose
        )
        
        # 4. Execute with Staggered Starts (Optimization)
        # Prevents API rate limits and initial congestion
        execution_tasks = []
        
        async def delayed_start(rid, tx, ty, delay):
            if delay > 0:
                print(f"⏳ [Orchestrator] Staggering {rid} start by {delay}s...")
                await asyncio.sleep(delay)
            return await orchestrator.worker_execution_loop(
                rid, tx, ty, manager_session_id, max_ticks=200
            )

        for i, (robot_id, (target_x, target_y)) in enumerate(tasks.items()):
            delay = i * 20  # 0s, 20s, 40s delays
            task = asyncio.create_task(delayed_start(robot_id, target_x, target_y, delay))
            execution_tasks.append(task)
            
        results = await asyncio.gather(*execution_tasks)
        
        # 5. Collect Metrics
        end_time = time.time()
        duration = end_time - start_time
        
        tasks_completed = sum(results)
        tasks_failed = len(results) - tasks_completed
        success_rate = tasks_completed / len(results) if results else 0
        
        # Recovery stats aggregation
        total_recoveries = sum(stats['attempts'] for stats in orchestrator.recovery_stats.values())
        recovery_successes = sum(stats['successes'] for stats in orchestrator.recovery_stats.values())
        recovery_success_rate = (recovery_successes / total_recoveries if total_recoveries > 0 else 0)
        
        # Strategy tracking
        all_strategies = []
        for stats in orchestrator.recovery_stats.values():
            all_strategies.extend(stats['strategies_used'])
        
        strategies_used = {
            strategy: all_strategies.count(strategy)
            for strategy in set(all_strategies)
        }
        
        robot_stats = {
            robot_id: {
                "attempts": stats['attempts'],
                "successes": stats['successes'],
                "strategies": stats['strategies_used']
            }
            for robot_id, stats in orchestrator.recovery_stats.items()
        }
        
        # 6. Compile Result
        trial_result = TrialResult(
            trial_id=trial_id,
            scenario_name=scenario['name'],
            start_positions=scenario['start_positions'],
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            tasks_assigned=len(tasks),
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            success_rate=success_rate,
            total_recoveries=total_recoveries,
            recovery_success_rate=recovery_success_rate,
            strategies_used=strategies_used,
            robot_stats=robot_stats
        )
        
        self.results.append(trial_result)
        
        print(f"\n📊 TRIAL COMPLETE:")
        print(f"  Duration: {duration:.2f}s")
        print(f"  Success Rate: {success_rate*100:.1f}%")
        print(f"  Recoveries: {total_recoveries} ({recovery_success_rate*100:.1f}% successful)")
        
        return trial_result
    
    async def run_full_evaluation(self, trials_per_scenario: int = 3, verbose: bool = False):
        """Run the complete suite of test scenarios."""
        scenarios = self.define_test_scenarios()
        
        print(f"\n{'='*70}")
        print(f"STARTING ENHANCED EVALUATION")
        print(f"Scenarios: {len(scenarios)}")
        print(f"Trials per scenario: {trials_per_scenario}")
        print(f"Total trials: {len(scenarios) * trials_per_scenario}")
        print(f"{'='*70}")
        
        for scenario in scenarios:
            for trial_num in range(1, trials_per_scenario + 1):
                await self.run_single_trial(scenario, trial_num, verbose)
                # Cooldown between trials to let async tasks cleanup
                await asyncio.sleep(5) 
        
        self.save_results_json()
        self.generate_visualizations()
        self.print_summary()
    
    def save_results_json(self):
        """Persist raw results to JSON for later analysis."""
        output_file = self.output_dir / f"enhanced_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        results_dict = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "total_trials": len(self.results),
                "scenarios": len(set(r.scenario_name for r in self.results)),
                "evaluation_type": "enhanced_forced_sticky_crossing"
            },
            "trials": [asdict(r) for r in self.results]
        }
        
        with open(output_file, 'w') as f:
            json.dump(results_dict, f, indent=2)
        
        print(f"\n✓ Results saved to {output_file}")
    
    def generate_visualizations(self):
        """Generate matplotlib charts for the evaluation report."""
        if not self.results:
            return
        
        #  
        # (This comment represents the output file generated below)
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Enhanced Agent Fleet Evaluation - Forced Sticky Zone Crossing', 
                     fontsize=16, fontweight='bold')
        
        # Chart 1: Recoveries per Trial
        ax1 = axes[0, 0]
        trial_numbers = range(1, len(self.results) + 1)
        recovery_counts = [r.total_recoveries for r in self.results]
        ax1.bar(trial_numbers, recovery_counts, color='steelblue')
        ax1.set_xlabel('Trial Number')
        ax1.set_ylabel('Total Recoveries')
        ax1.set_title('Recovery Events Per Trial (Should be > 0)')
        
        # Chart 2: Strategy Distribution
        ax2 = axes[0, 1]
        all_strategies = {}
        for result in self.results:
            for strategy, count in result.strategies_used.items():
                all_strategies[strategy] = all_strategies.get(strategy, 0) + count
        
        if all_strategies:
            ax2.pie(list(all_strategies.values()), labels=list(all_strategies.keys()), 
                   autopct='%1.1f%%', startangle=90, colors=plt.cm.Set3(range(len(all_strategies))))
            ax2.set_title('Recovery Strategy Distribution')
        else:
            ax2.text(0.5, 0.5, 'No recoveries recorded', ha='center', va='center')
        
        # Chart 3: Success Rate Trend
        ax3 = axes[1, 0]
        success_rates = [r.success_rate * 100 for r in self.results]
        ax3.plot(trial_numbers, success_rates, marker='o', color='green')
        ax3.set_xlabel('Trial Number')
        ax3.set_ylabel('Success Rate (%)')
        ax3.set_title('Success Rate Learning Curve')
        ax3.set_ylim(0, 105)
        
        # Chart 4: Duration vs Difficulty
        ax4 = axes[1, 1]
        durations = [r.duration for r in self.results]
        scatter = ax4.scatter(recovery_counts, durations, s=150, alpha=0.6, c=success_rates, cmap='RdYlGn')
        ax4.set_xlabel('Total Recoveries (Difficulty)')
        ax4.set_ylabel('Duration (s)')
        ax4.set_title('Task Duration vs Difficulty')
        plt.colorbar(scatter, ax=ax4, label='Success Rate %')
        
        plt.tight_layout()
        
        output_file = self.output_dir / f"enhanced_charts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        plt.savefig(output_file, dpi=300, bbox_inches='tight')
        print(f"✓ Visualizations saved to {output_file}")
    
    def print_summary(self):
        """Print console summary of the evaluation."""
        if not self.results:
            return
        
        total_trials = len(self.results)
        avg_success = np.mean([r.success_rate for r in self.results]) * 100
        total_recoveries = sum(r.total_recoveries for r in self.results)
        
        print(f"\n{'='*70}\nENHANCED EVALUATION SUMMARY\n{'='*70}")
        print(f"  Total Trials: {total_trials}")
        print(f"  Avg Success Rate: {avg_success:.1f}%")
        print(f"  Total Recoveries: {total_recoveries}")
        
        print(f"\nStrategy Effectiveness:")
        all_total = {}
        all_success = {}
        
        for result in self.results:
            for strategy, count in result.strategies_used.items():
                all_total[strategy] = all_total.get(strategy, 0) + count
                if result.recovery_success_rate > 0: # Simplified heuristic
                    all_success[strategy] = all_success.get(strategy, 0) + count
        
        for strategy, total in sorted(all_total.items()):
            # Effectiveness calc is approximate here based on trial outcome
            print(f"  {strategy}: used {total} times")


async def main():
    """Main entry point for the evaluation suite."""
    
    # 1. Clear LTM to demonstrate "Zero-Shot" learning capability
    print("\n🔄 Clearing recovery database for fresh learning demonstration...")
    db = RecoveryDatabase()
    db.clear()
    
    # 2. Run Evaluation
    evaluator = EnhancedEvaluationFramework(output_dir="evaluation_results")
    await evaluator.run_full_evaluation(trials_per_scenario=3, verbose=False)
    
    # 3. Generate Final Dashboard
    print("\n✓ Enhanced evaluation complete!")
    print("\nGenerating Enterprise Dashboard...")
    report = obs.generate_report()
    print(f"✓ Dashboard generated: enterprise_dashboard.json (Status: {report['status']})")


if __name__ == "__main__":
    asyncio.run(main())