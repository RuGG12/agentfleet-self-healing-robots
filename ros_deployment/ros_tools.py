#!/usr/bin/env python3
"""
ros_tools.py
Description: ROS2 implementation of the Navigation, Status, and Recovery tools.
             Directly interfaces with Gazebo/Nav2 stack via rclpy.
             Features aggressive recovery logic for sticky zones.

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

# --- Configuration ---
GRID_SCALE = 1.0 
STICKY_ZONE_METERS = {"x_min": 5.0, "x_max": 7.0, "y_min": 5.0, "y_max": 7.0}


class AgentFleetNode(Node):
    """
    Main ROS node for the fleet.
    Handles Pub/Sub for all 3 robots in a single node to simplify orchestration.
    """
    def __init__(self):
        super().__init__('agent_fleet_node')
        self.robots = ["robot_1", "robot_2", "robot_3"]
        self.pubs = {}
        self.robot_states = {}
        
        qos = QoSProfile(depth=10) 

        for rid in self.robots:
            self.pubs[rid] = self.create_publisher(Twist, f'/{rid}/cmd_vel', qos)
            self.create_subscription(Odometry, f'/{rid}/odom', lambda msg, r=rid: self.odom_callback(msg, r), qos)
            self.robot_states[rid] = {"pose": [0.0, 0.0], "yaw": 0.0, "target": None, "status": "IDLE"}
            
        print(f"[ROS] Node Initialized. Sticky Zone: 5.0m - 7.0m")

    def check_connection(self, robot_id):
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

        # Sticky Zone Logic
        if (STICKY_ZONE_METERS["x_min"] <= x <= STICKY_ZONE_METERS["x_max"] and 
            STICKY_ZONE_METERS["y_min"] <= y <= STICKY_ZONE_METERS["y_max"]):
            
            if self.robot_states[robot_id]["status"] == "NAVIGATING":
                 print(f"\n🚨 {robot_id} HIT STICKY ZONE at ({x:.2f}, {y:.2f})! STOPPING! 🚨\n")
                 self.robot_states[robot_id]["status"] = "STUCK"
                 self.move_robot(robot_id, 0.0, 0.0)

    def move_robot(self, robot_id: str, linear: float, angular: float):
        msg = Twist()
        msg.linear.x = float(linear)
        msg.angular.z = float(angular)
        self.pubs[robot_id].publish(msg)

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
    """ROS-based navigation tool."""
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
    """ROS-based recovery maneuver tool."""
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
