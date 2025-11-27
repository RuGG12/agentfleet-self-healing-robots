#!/usr/bin/env python3
"""
fleet_launch.py
Description: Launch file for AgentFleet ROS2 integration.
             Starts Gazebo, Nav2, and spawns 3 robots.

Usage:
    ros2 launch agentfleet fleet_launch.py

Author: Rugved Raote
Competition: Google AI Agents Intensive - Capstone
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    """Generate launch description for 3-robot fleet."""
    
    # Package directories
    pkg_gazebo_ros = FindPackageShare('gazebo_ros')
    pkg_nav2_bringup = FindPackageShare('nav2_bringup')
    pkg_turtlebot3_gazebo = FindPackageShare('turtlebot3_gazebo')
    
    # World file
    world_file = PathJoinSubstitution([
        FindPackageShare('agentfleet'),
        'worlds',
        'warehouse.world'
    ])
    
    # Robot model
    robot_model = 'burger'  # Use TurtleBot3 Burger
    
    # Launch Gazebo with warehouse world
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            pkg_gazebo_ros, '/launch/gazebo.launch.py'
        ]),
        launch_arguments={
            'world': world_file,
            'verbose': 'true'
        }.items()
    )
    
    # Robot spawn positions (matching your sim)
    robots = [
        {'name': 'robot_1', 'x': '0.0', 'y': '0.0', 'z': '0.01'},
        {'name': 'robot_2', 'x': '0.0', 'y': '1.0', 'z': '0.01'},
        {'name': 'robot_3', 'x': '1.0', 'y': '0.0', 'z': '0.01'},
    ]
    
    robot_nodes = []
    nav2_nodes = []
    
    for robot in robots:
        namespace = robot['name']
        
        # Spawn robot in Gazebo
        spawn_robot = Node(
            package='gazebo_ros',
            executable='spawn_entity.py',
            arguments=[
                '-entity', robot['name'],
                '-topic', f'/{namespace}/robot_description',
                '-x', robot['x'],
                '-y', robot['y'],
                '-z', robot['z'],
            ],
            output='screen'
        )
        robot_nodes.append(spawn_robot)
        
        # Robot state publisher
        robot_state_publisher = Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            namespace=namespace,
            parameters=[{
                'use_sim_time': True,
                'robot_description': LaunchConfiguration(f'{namespace}_description')
            }],
            output='screen'
        )
        robot_nodes.append(robot_state_publisher)
        
        # Nav2 for each robot
        nav2_params = PathJoinSubstitution([
            FindPackageShare('agentfleet'),
            'config',
            f'{namespace}_nav2_params.yaml'
        ])
        
        nav2_launch = IncludeLaunchDescription(
            PythonLaunchDescriptionSource([
                pkg_nav2_bringup, '/launch/navigation_launch.py'
            ]),
            launch_arguments={
                'namespace': namespace,
                'use_sim_time': 'True',
                'params_file': nav2_params,
                'autostart': 'True'
            }.items()
        )
        nav2_nodes.append(nav2_launch)
    
    # RViz for visualization
    rviz_config = PathJoinSubstitution([
        FindPackageShare('agentfleet'),
        'rviz',
        'fleet_view.rviz'
    ])
    
    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': True}],
        output='screen'
    )
    
    return LaunchDescription([
        gazebo,
        *robot_nodes,
        *nav2_nodes,
        rviz
    ])
