#!/usr/bin/env python3
"""
spawn_fleet.py
Description: Script to spawn the robot fleet into the Gazebo simulation.
             Uses fixed positions to avoid initial collisions.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import os
import time
import subprocess
import sys

# BASE URDF PATH
BASE_URDF = "/opt/ros/humble/share/turtlebot3_description/urdf/turtlebot3_burger.urdf"

# Robot Start Positions
ROBOTS = [
    {"name": "robot_1", "x": 0.5, "y": 0.5, "z": 0.2}, 
    {"name": "robot_2", "x": 2.5, "y": 1.0, "z": 0.2}, 
    {"name": "robot_3", "x": 2.0, "y": 2.0, "z": 0.2}, 
]

def get_base_xml():
    """Reads the base TurtleBot3 URDF."""
    if not os.path.exists(BASE_URDF):
        print(f"❌ CRITICAL: Base URDF not found at {BASE_URDF}")
        sys.exit(1)
    return subprocess.check_output(["xacro", BASE_URDF], text=True)

def create_robot_urdf(name, base_xml):
    """Injects namespaced Gazebo plugins into the URDF."""
    plugin_block = f'''
  <gazebo>
    <plugin name="turtlebot3_diff_drive" filename="libgazebo_ros_diff_drive.so">
      <ros>
        <namespace>/{name}</namespace>
        <remapping>cmd_vel:=cmd_vel</remapping>
        <remapping>odom:=odom</remapping>
      </ros>
      <update_rate>30</update_rate>
      <left_joint>wheel_left_joint</left_joint>
      <right_joint>wheel_right_joint</right_joint>
      <wheel_separation>0.160</wheel_separation>
      <wheel_diameter>0.066</wheel_diameter>
      <max_wheel_torque>20</max_wheel_torque>
      <max_wheel_acceleration>1.0</max_wheel_acceleration>
      <command_topic>cmd_vel</command_topic>
      <publish_odom>true</publish_odom>
      <publish_odom_tf>true</publish_odom_tf>
      <publish_wheel_tf>false</publish_wheel_tf>
      <odometry_topic>odom</odometry_topic>
      <odometry_frame>{name}/odom</odometry_frame>
      <robot_base_frame>{name}/base_footprint</robot_base_frame>
    </plugin>

    <plugin name="turtlebot3_joint_state" filename="libgazebo_ros_joint_state_publisher.so">
      <ros>
        <namespace>/{name}</namespace>
        <remapping>~/out:=joint_states</remapping>
      </ros>
      <update_rate>30</update_rate>
      <joint_name>wheel_left_joint</joint_name>
      <joint_name>wheel_right_joint</joint_name>
    </plugin>
  </gazebo>
</robot>
'''
    xml = base_xml.replace('</robot>', '') + plugin_block
    filename = f"/tmp/{name}_full.urdf"
    with open(filename, "w") as f: f.write(xml)
    return filename

def main():
    print("☢️  INITIATING NUCLEAR SPAWN SEQUENCE...")
    base_xml = get_base_xml()
    for bot in ROBOTS:
        name = bot["name"]
        print(f"   🔨 Forging URDF for {name}...")
        urdf_file = create_robot_urdf(name, base_xml)
        print(f"   🚀 Spawning {name} at ({bot['x']}, {bot['y']})...")
        cmd = (f"ros2 run gazebo_ros spawn_entity.py -entity {name} -file {urdf_file} "
               f"-x {bot['x']} -y {bot['y']} -z {bot['z']} > /dev/null 2>&1")
        os.system(cmd)
        time.sleep(2)
    print("✅ FLEET DEPLOYED.")

if __name__ == "__main__":
    main()
