#!/usr/bin/env python3
"""
verify_hal.py
Description: Verification script for the AgentFleet C++ HAL module.
             Tests that the module is importable and functional.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import sys
import os
import time
from typing import List, Tuple

# Add build directory to path for local testing
sys.path.insert(0, './build')
sys.path.insert(0, './lib')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'build'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ros_deployment'))


def print_header(title: str):
    """Print formatted test header."""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def print_result(test_name: str, passed: bool, details: str = ""):
    """Print formatted test result."""
    icon = "✓" if passed else "✗"
    status = "PASS" if passed else "FAIL"
    print(f"  {icon} [{status}] {test_name}")
    if details:
        print(f"          {details}")


def test_module_import() -> Tuple[bool, str]:
    """Test that the C++ module can be imported."""
    try:
        import agentfleet_cpp
        version = getattr(agentfleet_cpp, '__version__', 'unknown')
        has_ros2 = getattr(agentfleet_cpp, 'HAS_ROS2', False)
        return True, f"v{version}, ROS2={has_ros2}"
    except ImportError as e:
        return False, str(e)


def test_robot_hal() -> Tuple[bool, str]:
    """Test RobotHAL class instantiation and basic operations."""
    try:
        import agentfleet_cpp
        
        # Create HAL instance
        hal = agentfleet_cpp.RobotHAL("test_robot_1")
        
        # Test getters
        pose = hal.get_pose()
        yaw = hal.get_yaw()
        status = hal.get_status()
        robot_id = hal.get_robot_id()
        connected = hal.is_connected()
        
        # Test cmd_vel (should succeed in standalone mode)
        result = hal.publish_cmd_vel(0.5, 0.1)
        
        # Test fault injection
        hal.inject_fault("motor_timeout")
        assert hal.has_fault(), "Fault should be active"
        
        blocked_result = hal.publish_cmd_vel(0.5, 0.0)
        assert not blocked_result, "cmd_vel should be blocked by fault"
        
        hal.clear_faults()
        assert not hal.has_fault(), "Faults should be cleared"
        
        return True, f"robot_id={robot_id}, connected={connected}"
    except Exception as e:
        return False, str(e)


def test_collision_checker() -> Tuple[bool, str]:
    """Test CollisionChecker class."""
    try:
        import agentfleet_cpp
        
        checker = agentfleet_cpp.CollisionChecker()
        
        # Set sticky zone
        checker.set_sticky_zone(5, 7, 5, 7)
        checker.set_grid_size(10, 10)
        
        # Test sticky zone detection
        assert checker.is_in_sticky_zone(6.0, 6.0), "Point (6,6) should be in sticky zone"
        assert not checker.is_in_sticky_zone(0.0, 0.0), "Point (0,0) should not be in sticky zone"
        assert not checker.is_in_sticky_zone(8.0, 8.0), "Point (8,8) should not be in sticky zone"
        
        # Test bounds checking
        assert checker.is_in_bounds(5.0, 5.0), "Point (5,5) should be in bounds"
        assert not checker.is_in_bounds(-1.0, 5.0), "Point (-1,5) should be out of bounds"
        
        # Test batch waypoint checking
        waypoints = [[0, 0], [3, 3], [6, 6], [9, 9]]
        results = checker.check_waypoints(waypoints)
        assert results[2] == True, "Waypoint (6,6) should be in sticky zone"
        assert results[0] == False, "Waypoint (0,0) should not be in sticky zone"
        
        # Test path conflict detection
        fleet_positions = {"robot_2": [5.0, 5.0], "robot_3": [8.0, 8.0]}
        fleet_targets = {"robot_2": [6.0, 6.0], "robot_3": [9.0, 9.0]}
        
        # Conflict: robot_1 wants to go where robot_2 is heading
        conflict = checker.check_path_conflict(
            "robot_1", 6.0, 6.0, 
            fleet_positions, fleet_targets
        )
        assert conflict, "Should detect conflict with robot_2's target"
        
        # No conflict: robot_1 goes to unoccupied location
        no_conflict = checker.check_path_conflict(
            "robot_1", 1.0, 1.0,
            fleet_positions, fleet_targets
        )
        assert not no_conflict, "Should not detect conflict for (1,1)"
        
        return True, "All collision checks passed"
    except Exception as e:
        return False, str(e)


def test_path_smoothing() -> Tuple[bool, str]:
    """Test path smoothing functions."""
    try:
        import agentfleet_cpp
        
        # Create a rough path
        path = [[0, 0], [5, 5], [10, 0]]
        
        # Test Catmull-Rom smoothing
        smoothed = agentfleet_cpp.smooth_path(path, 10)
        assert len(smoothed) > len(path), f"Smoothed path should have more points ({len(smoothed)} vs {len(path)})"
        
        # Test Bezier smoothing
        bezier = agentfleet_cpp.bezier_smooth(path, 0.5)
        assert len(bezier) > len(path), "Bezier smoothed path should have more points"
        
        # Test path length calculation
        length = agentfleet_cpp.path_length(path)
        assert length > 0, "Path length should be positive"
        
        # Test path resampling
        resampled = agentfleet_cpp.resample_path(path, 1.0)
        assert len(resampled) >= 2, "Resampled path should have at least 2 points"
        
        # Test sharp turn detection
        is_sharp = agentfleet_cpp.is_sharp_turn([0, 0], [5, 5], [10, 0])
        # 90 degree turn should be sharp with default threshold of 45 degrees
        assert is_sharp, "90 degree turn should be detected as sharp"
        
        return True, f"smooth={len(smoothed)}pts, bezier={len(bezier)}pts, length={length:.2f}m"
    except Exception as e:
        return False, str(e)


def test_hal_wrapper() -> Tuple[bool, str]:
    """Test the Python HAL wrapper with fallback support."""
    try:
        from hal_wrapper import (
            HALInterface, CollisionCheckerInterface, 
            smooth_path, is_hal_available, get_hal_version
        )
        
        hal_available = is_hal_available()
        version = get_hal_version()
        
        # Test HAL Interface
        hal = HALInterface("wrapper_test_robot")
        impl = hal.implementation
        
        pose = hal.get_pose()
        hal.inject_fault("packet_drop")
        hal.clear_faults()
        
        # Test Collision Checker Interface
        checker = CollisionCheckerInterface()
        checker.set_sticky_zone(5, 7, 5, 7)
        in_zone = checker.is_in_sticky_zone(6.0, 6.0)
        assert in_zone, "Point should be in sticky zone"
        
        # Test path smoothing via wrapper
        path = [[0, 0], [5, 5], [10, 0]]
        smoothed = smooth_path(path)
        assert len(smoothed) > len(path), "Path should be smoothed"
        
        return True, f"impl={impl}, version={version}, hal_available={hal_available}"
    except Exception as e:
        return False, str(e)


def test_performance() -> Tuple[bool, str]:
    """Test performance of C++ vs Python collision checking."""
    try:
        import agentfleet_cpp
        
        checker = agentfleet_cpp.CollisionChecker()
        checker.set_sticky_zone(5, 7, 5, 7)
        
        # Generate test points
        num_checks = 10000
        import random
        random.seed(42)
        points = [[random.uniform(0, 10), random.uniform(0, 10)] for _ in range(num_checks)]
        
        # Time C++ implementation
        start = time.perf_counter()
        for p in points:
            checker.is_in_sticky_zone(p[0], p[1])
        cpp_time = time.perf_counter() - start
        
        # Time Python implementation
        sticky = {"x_min": 5, "x_max": 7, "y_min": 5, "y_max": 7}
        start = time.perf_counter()
        for p in points:
            _ = (sticky["x_min"] <= p[0] <= sticky["x_max"] and 
                 sticky["y_min"] <= p[1] <= sticky["y_max"])
        py_time = time.perf_counter() - start
        
        speedup = py_time / cpp_time if cpp_time > 0 else 0
        
        return True, f"{num_checks} checks: C++={cpp_time*1000:.2f}ms, Python={py_time*1000:.2f}ms, speedup={speedup:.1f}x"
    except Exception as e:
        return False, str(e)


def main():
    """Run all verification tests."""
    print_header("AgentFleet C++ HAL Verification")
    
    tests = [
        ("Module Import", test_module_import),
        ("RobotHAL Class", test_robot_hal),
        ("CollisionChecker Class", test_collision_checker),
        ("Path Smoothing Functions", test_path_smoothing),
        ("HAL Wrapper (with fallback)", test_hal_wrapper),
        ("Performance Benchmark", test_performance),
    ]
    
    results = []
    cpp_available = False
    
    # First check if C++ module is available
    try:
        import agentfleet_cpp
        cpp_available = True
    except ImportError:
        print("\n⚠ C++ module not available - testing fallback mode only")
    
    print_header("Test Results")
    
    for test_name, test_func in tests:
        # Skip C++-only tests if module not available
        if not cpp_available and test_name not in ["Module Import", "HAL Wrapper (with fallback)"]:
            print_result(test_name, False, "Skipped - C++ module not available")
            results.append((test_name, False))
            continue
        
        try:
            passed, details = test_func()
            print_result(test_name, passed, details)
            results.append((test_name, passed))
        except Exception as e:
            print_result(test_name, False, f"Exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print_header("Summary")
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    if cpp_available:
        print(f"\n  C++ HAL: AVAILABLE")
    else:
        print(f"\n  C++ HAL: NOT AVAILABLE (fallback mode)")
    
    print(f"  Tests Passed: {passed}/{total}")
    
    if passed == total:
        print("\n  🎉 All verification tests PASSED!")
        return 0
    else:
        print(f"\n  ⚠ {total - passed} test(s) FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
