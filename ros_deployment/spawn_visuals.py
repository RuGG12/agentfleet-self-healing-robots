#!/usr/bin/env python3
"""
spawn_visuals.py
Description: Spawns visual markers for the 'Sticky Zone' and walls in Gazebo.

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import os

# Configuration
# Center of 5 and 7 is 6. Width is 2.
STICKY_X = 6.0
STICKY_Y = 6.0
STICKY_W = 2.0
STICKY_H = 2.0

def spawn_sticky_zone():
    """Spawns a red semi-transparent plane indicating the danger zone."""
    print("🎨 Painting 5-7m Zone...")
    sdf = f"""<?xml version='1.0'?><sdf version='1.6'><model name='sticky_zone_visual'><static>true</static><link name='link'><pose>{STICKY_X} {STICKY_Y} 0.01 0 0 0</pose><visual name='visual'><geometry><plane><normal>0 0 1</normal><size>{STICKY_W} {STICKY_H}</size></plane></geometry><material><ambient>1 0 0 0.6</ambient><diffuse>1 0 0 0.6</diffuse></material></visual></link></model></sdf>"""
    with open("/tmp/sticky_zone.sdf", "w") as f: f.write(sdf.strip())
    os.system("ros2 service call /delete_entity gazebo_msgs/srv/DeleteEntity \"{name: 'sticky_zone_visual'}\" > /dev/null 2>&1")
    os.system("ros2 run gazebo_ros spawn_entity.py -entity sticky_zone_visual -file /tmp/sticky_zone.sdf -x 0 -y 0 -z 0")

def spawn_walls():
    """Spawns walls to enclose the warehouse arena."""
    print("🧱 Building Walls...")
    grey = "<material><ambient>0.5 0.5 0.5 1</ambient><diffuse>0.5 0.5 0.5 1</diffuse></material>"
    walls = [("wall_S", 5, -0.5, 11, 0.2), ("wall_N", 5, 10.5, 11, 0.2), ("wall_W", -0.5, 5, 0.2, 11), ("wall_E", 10.5, 5, 0.2, 11)]
    for n,x,y,lx,ly in walls:
        sdf = f"""<?xml version='1.0'?><sdf version='1.6'><model name='{n}'><static>true</static><link name='link'><pose>{x} {y} 0.5 0 0 0</pose><visual name='visual'><geometry><box><size>{lx} {ly} 1.0</size></box></geometry>{grey}</visual></link></model></sdf>"""
        with open(f"/tmp/{n}.sdf", "w") as f: f.write(sdf.strip())
        os.system(f"ros2 run gazebo_ros spawn_entity.py -entity {n} -file /tmp/{n}.sdf -x 0 -y 0 -z 0 > /dev/null 2>&1")

if __name__ == "__main__": 
    spawn_sticky_zone()
    spawn_walls()
