#!/usr/bin/env python3
"""
ros_tools.py
Description: ROS2 implementation of the Navigation, Status, and Recovery tools.
             Now integrated with C++ Hardware Abstraction Layer for low-latency
             control and optimized collision detection.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import threading
import time
import math
from typing import Dict, Any

# --- Local Project Imports ---
from tool_api import BaseNavigator, BaseCritic, BaseRecovery

# --- HAL Integration ---
try:
    from hal_wrapper import HALInterface, CollisionCheckerInterface, is_hal_available
    USE_HAL = is_hal_available()
    if USE_HAL:
        print("[ROS] Using C++ HAL for low-latency control")
    else:
        print("[ROS] C++ HAL not available, using Python ROS implementation")
except ImportError:
    USE_HAL = False
    print("[ROS] HAL wrapper not found, using Python ROS implementation")

# --- Configuration ---
GRID_SCALE = 1.0 
STICKY_ZONE_METERS = {"x_min": 5.0, "x_max": 7.0, "y_min": 5.0, "y_max": 7.0}

# Initialize collision checker
_collision_checker = None
def get_collision_checker():
    """Get or create the singleton collision checker."""
    global _collision_checker
    if _collision_checker is None:
        try:
            _collision_checker = CollisionCheckerInterface()
            _collision_checker.set_sticky_zone(
                int(STICKY_ZONE_METERS["x_min"]),
                int(STICKY_ZONE_METERS["x_max"]),
                int(STICKY_ZONE_METERS["y_min"]),
                int(STICKY_ZONE_METERS["y_max"])
            )
        except Exception as e:
            print(f"[ROS] Warning: Could not initialize collision checker: {e}")
            _collision_checker = None
    return _collision_checker


class AgentFleetNode(Node):
    """
    Main ROS node for the fleet.
    Handles Pub/Sub for all 3 robots in a single node to simplify orchestration.
    Now integrates with C++ HAL for improved performance.
    """
    def __init__(self):
        super().__init__('agent_fleet_node')
        self.robots = ["robot_1", "robot_2", "robot_3"]
        self.pubs = {}
        self.robot_states = {}
        self.hal_interfaces = {}  # C++ HAL interfaces per robot
        
        qos = QoSProfile(depth=10)

        for rid in self.robots:
            # Initialize C++ HAL if available
            if USE_HAL:
                try:
                    self.hal_interfaces[rid] = HALInterface(rid)
                    print(f"[ROS] HAL initialized for {rid}")
                except Exception as e:
                    print(f"[ROS] HAL init failed for {rid}: {e}")
                    self.hal_interfaces[rid] = None
            else:
                self.hal_interfaces[rid] = None
            
            # Standard ROS pub/sub (fallback or for features not in HAL)
            self.pubs[rid] = self.create_publisher(Twist, f'/{rid}/cmd_vel', qos)
            self.create_subscription(Odometry, f'/{rid}/odom', 
                                    lambda msg, r=rid: self.odom_callback(msg, r), qos)
            self.robot_states[rid] = {
                "pose": [0.0, 0.0], 
                "yaw": 0.0, 
                "target": None, 
                "status": "IDLE"
            }
            
        hal_status = "C++ HAL" if USE_HAL else "Python"
        print(f"[ROS] Node Initialized ({hal_status}). Sticky Zone: 5.0m - 7.0m")

    def check_connection(self, robot_id):
        # Check C++ HAL connection first
        hal = self.hal_interfaces.get(robot_id)
        if hal and hal.is_connected():
            return True
        # Fallback to ROS subscriber count
        subs = self.count_subscribers(f'/{robot_id}/cmd_vel')
        return subs > 0

    def odom_callback(self, msg: Odometry, robot_id: str):
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        
        q = msg.pose.pose.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        self.robot_states[robot_id]["pose"] = [x, y]
        self.robot_states[robot_id]["yaw"] = yaw

        # Sticky Zone Logic - use C++ collision checker if available
        checker = get_collision_checker()
        in_sticky_zone = False
        
        if checker:
            in_sticky_zone = checker.is_in_sticky_zone(x, y)
        else:
            # Fallback to Python check
            in_sticky_zone = (STICKY_ZONE_METERS["x_min"] <= x <= STICKY_ZONE_METERS["x_max"] and 
                             STICKY_ZONE_METERS["y_min"] <= y <= STICKY_ZONE_METERS["y_max"])
        
        if in_sticky_zone:
            if self.robot_states[robot_id]["status"] == "NAVIGATING":
                print(f"\n🚨 {robot_id} HIT STICKY ZONE at ({x:.2f}, {y:.2f})! STOPPING! 🚨\n")
                self.robot_states[robot_id]["status"] = "STUCK"
                self.move_robot(robot_id, 0.0, 0.0)

    def move_robot(self, robot_id: str, linear: float, angular: float):
        """
        Send velocity command to robot.
        Uses C++ HAL for low-latency publishing if available.
        """
        hal = self.hal_interfaces.get(robot_id)
        
        if hal:
            # Use C++ HAL for low-latency command
            success = hal.publish_cmd_vel(float(linear), float(angular))
            if not success:
                # HAL blocked (fault injected), log it
                print(f"[ROS] HAL blocked cmd_vel for {robot_id} (fault active)")
        else:
            # Fallback to Python ROS
            msg = Twist()
            msg.linear.x = float(linear)
            msg.angular.z = float(angular)
            self.pubs[robot_id].publish(msg)
    
    def inject_fault(self, robot_id: str, fault_type: str):
        """
        Inject a simulated hardware fault via the C++ HAL.
        
        Args:
            robot_id: Target robot
            fault_type: 'motor_timeout', 'packet_drop', or 'sensor_freeze'
        """
        hal = self.hal_interfaces.get(robot_id)
        if hal:
            hal.inject_fault(fault_type)
            print(f"[ROS] Fault '{fault_type}' injected on {robot_id}")
        else:
            print(f"[ROS] Cannot inject fault - HAL not available for {robot_id}")
    
    def clear_faults(self, robot_id: str):
        """Clear all faults on a robot."""
        hal = self.hal_interfaces.get(robot_id)
        if hal:
            hal.clear_faults()
            print(f"[ROS] Faults cleared on {robot_id}")

# Global Node Singleton
_node = None
def get_node():
    global _node
    if _node is None:
        rclpy.init()
        _node = AgentFleetNode()
        threading.Thread(target=rclpy.spin, args=(_node,), daemon=True).start()
    return _node


class Navigator(BaseNavigator):
    """ROS-based navigation tool with C++ HAL integration."""
    def __init__(self, robot_id: str):
        super().__init__(robot_id)
        self.node = get_node()

    def go_to_pose(self, x: float, y: float) -> Dict[str, Any]:
        self.node.check_connection(self.robot_id)
        tx = x * GRID_SCALE
        ty = y * GRID_SCALE
        
        if self.node.robot_states[self.robot_id]["status"] == "NAVIGATING":
            self.node.robot_states[self.robot_id]["status"] = "IDLE"
            time.sleep(0.2) 

        self.node.robot_states[self.robot_id]["target"] = [tx, ty]
        self.node.robot_states[self.robot_id]["status"] = "NAVIGATING"
        threading.Thread(target=self._drive_loop, args=(tx, ty), daemon=True).start()
        return {"status": "NAVIGATING", "message": f"Moving to ({tx}, {ty})"}

    def _drive_loop(self, tx, ty):
        print(f"[{self.robot_id}] >>> Driving to ({tx}, {ty})")
        while self.node.robot_states[self.robot_id]["status"] == "NAVIGATING":
            curr = self.node.robot_states[self.robot_id]["pose"]
            yaw = self.node.robot_states[self.robot_id]["yaw"]
            
            dx = tx - curr[0]
            dy = ty - curr[1]
            dist = math.sqrt(dx*dx + dy*dy)
            target_angle = math.atan2(dy, dx)
            angle_diff = target_angle - yaw
            while angle_diff > math.pi: angle_diff -= 2*math.pi
            while angle_diff < -math.pi: angle_diff += 2*math.pi
            
            if dist < 0.2:
                self.node.robot_states[self.robot_id]["status"] = "IDLE"
                self.node.move_robot(self.robot_id, 0.0, 0.0)
                break

            if abs(angle_diff) > 0.2:
                speed = 0.8 if angle_diff > 0 else -0.8
                self.node.move_robot(self.robot_id, 0.0, speed)
            else:
                self.node.move_robot(self.robot_id, 0.6, angle_diff)
            
            time.sleep(0.1)


class Critic(BaseCritic):
    """ROS-based status checking tool."""
    def __init__(self, robot_id: str):
        super().__init__(robot_id)
        self.node = get_node()

    def get_status(self) -> Dict[str, Any]:
        state = self.node.robot_states[self.robot_id]
        rx = int(round(state["pose"][0]))
        ry = int(round(state["pose"][1]))
        return {"state": state["status"], "pose": [rx, ry], "target": [0,0]}


class Recovery(BaseRecovery):
    """ROS-based recovery maneuver tool with HAL integration."""
    def __init__(self, robot_id: str):
        super().__init__(robot_id)
        self.node = get_node()

    def execute_recovery(self, strategy: str) -> Dict[str, Any]:
        print(f"[{self.robot_id}] 🚑 RECOVERING: {strategy}")
        
        self.node.robot_states[self.robot_id]["status"] = "RECOVERING"
        
        # 1. REVERSE (Back up 1.5m)
        if "reverse" in strategy:
            self.node.move_robot(self.robot_id, -0.5, 0.0)
            time.sleep(3.0) 
        
        # 2. TURN (90 degrees)
        if "left" in strategy:
            self.node.move_robot(self.robot_id, 0.0, 0.8)
            time.sleep(2.0) 
        elif "right" in strategy:
            self.node.move_robot(self.robot_id, 0.0, -0.8)
            time.sleep(2.0) 

        # 3. FORWARD PUSH
        if "forward" in strategy:
            self.node.move_robot(self.robot_id, 0.5, 0.0)
            time.sleep(3.0) 
            
        self.node.move_robot(self.robot_id, 0.0, 0.0)
        self.node.robot_states[self.robot_id]["status"] = "IDLE"
        return {"status": "RECOVERY_COMPLETE", "message": "Done"}


# =============================================================================
# Fault Injection API (for testing)
# =============================================================================

def inject_fault(robot_id: str, fault_type: str):
    """
    Inject a simulated hardware fault on a robot.
    
    Args:
        robot_id: Target robot (e.g., "robot_1")
        fault_type: One of 'motor_timeout', 'packet_drop', 'sensor_freeze'
    """
    node = get_node()
    node.inject_fault(robot_id, fault_type)


def clear_faults(robot_id: str):
    """Clear all faults on a robot."""
    node = get_node()
    node.clear_faults(robot_id)


def get_hal_status() -> Dict[str, Any]:
    """Get HAL availability status for all robots."""
    node = get_node()
    status = {"hal_available": USE_HAL, "robots": {}}
    
    for rid in node.robots:
        hal = node.hal_interfaces.get(rid)
        status["robots"][rid] = {
            "hal_connected": hal.is_connected() if hal else False,
            "has_fault": hal.has_fault() if hal else False
        }
    
    return status
