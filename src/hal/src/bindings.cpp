/**
 * @file bindings.cpp
 * @brief pybind11 bindings for AgentFleet C++ HAL
 *
 * Exposes RobotHAL, CollisionChecker, and path smoothing functions to Python.
 *
 * @author Rugved Raote
 * @copyright 2025 AgentFleet Project
 */

#include <pybind11/operators.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>


#include "collision_checker.hpp"
#include "path_smoother.hpp"
#include "robot_hal.hpp"


namespace py = pybind11;
using namespace agentfleet;

PYBIND11_MODULE(agentfleet_cpp, m) {
  m.doc() = R"doc(
        AgentFleet C++ Hardware Abstraction Layer
        
        High-performance C++ library for robot control, collision detection,
        and path smoothing. Provides low-latency ROS 2 integration and
        fault injection for testing self-healing algorithms.
        
        Example:
            >>> import agentfleet_cpp
            >>> hal = agentfleet_cpp.RobotHAL("robot_1")
            >>> hal.publish_cmd_vel(0.5, 0.0)
            >>> pose = hal.get_pose()
    )doc";

  // =========================================================================
  // Enums
  // =========================================================================

  py::enum_<FaultState>(m, "FaultState", "Hardware fault states for simulation")
      .value("NONE", FaultState::NONE, "No active fault")
      .value("MOTOR_TIMEOUT", FaultState::MOTOR_TIMEOUT, "Motors unresponsive")
      .value("PACKET_DROP", FaultState::PACKET_DROP, "Random packet loss (50%)")
      .value("SENSOR_FREEZE", FaultState::SENSOR_FREEZE, "Sensor data frozen")
      .export_values();

  py::enum_<RobotStatus>(m, "RobotStatus", "Robot operational status")
      .value("IDLE", RobotStatus::IDLE)
      .value("NAVIGATING", RobotStatus::NAVIGATING)
      .value("STUCK", RobotStatus::STUCK)
      .value("RECOVERING", RobotStatus::RECOVERING)
      .value("FAULT", RobotStatus::FAULT)
      .export_values();

  // =========================================================================
  // RobotHAL Class
  // =========================================================================

  py::class_<RobotHAL>(m, "RobotHAL", R"doc(
        Hardware Abstraction Layer for a single robot.
        
        Provides thread-safe access to robot state and low-latency command
        publishing via ROS 2. Supports fault injection for testing.
        
        Args:
            robot_id: Unique robot identifier (e.g., "robot_1")
        
        Example:
            >>> hal = RobotHAL("robot_1")
            >>> hal.publish_cmd_vel(0.5, 0.0)  # Move forward
            >>> x, y = hal.get_pose()
            >>> hal.inject_fault("motor_timeout")  # Test fault handling
    )doc")
      .def(py::init<const std::string &>(), py::arg("robot_id"),
           "Create HAL instance for the specified robot")

      // Command publishing
      .def("publish_cmd_vel", &RobotHAL::publish_cmd_vel, py::arg("linear_x"),
           py::arg("angular_z"),
           "Publish velocity command. Returns False if blocked by fault.")
      .def("stop", &RobotHAL::stop, "Stop the robot immediately")

      // State getters
      .def("get_pose", &RobotHAL::get_pose,
           "Get current [x, y] position in meters")
      .def("get_yaw", &RobotHAL::get_yaw, "Get current yaw angle in radians")
      .def("get_status", &RobotHAL::get_status, "Get robot status as string")
      .def("get_robot_id", &RobotHAL::get_robot_id, "Get robot identifier")
      .def("is_connected", &RobotHAL::is_connected,
           "Check if HAL is connected to ROS")

      // Status management
      .def("set_status", &RobotHAL::set_status, py::arg("status"),
           "Set robot operational status")
      .def("set_target", &RobotHAL::set_target, py::arg("x"), py::arg("y"),
           "Set target position for navigation")
      .def("get_target", &RobotHAL::get_target,
           "Get current target [x, y] coordinates")

      // Fault injection
      .def("inject_fault", &RobotHAL::inject_fault, py::arg("fault_type"),
           "Inject fault: 'motor_timeout', 'packet_drop', or 'sensor_freeze'")
      .def("clear_faults", &RobotHAL::clear_faults, "Clear all active faults")
      .def("get_fault_state", &RobotHAL::get_fault_state,
           "Get current fault state")
      .def("has_fault", &RobotHAL::has_fault, "Check if any fault is active")

      // Properties
      .def_property_readonly("robot_id", &RobotHAL::get_robot_id)
      .def_property_readonly("connected", &RobotHAL::is_connected);

  // =========================================================================
  // CollisionChecker Class
  // =========================================================================

  py::class_<CollisionChecker>(m, "CollisionChecker", R"doc(
        Fast 2D grid-based collision checker.
        
        Provides efficient collision detection for sticky zones and
        fleet conflict resolution.
        
        Example:
            >>> checker = CollisionChecker()
            >>> checker.set_sticky_zone(5, 7, 5, 7)
            >>> checker.is_in_sticky_zone(6.0, 6.0)  # True
    )doc")
      .def(py::init<>())

      // Configuration
      .def("set_grid_size", &CollisionChecker::set_grid_size, py::arg("width"),
           py::arg("height"), "Set grid dimensions in cells")
      .def("set_sticky_zone", &CollisionChecker::set_sticky_zone,
           py::arg("x_min"), py::arg("x_max"), py::arg("y_min"),
           py::arg("y_max"), "Set sticky zone bounds")

      // Collision detection
      .def("is_in_sticky_zone", &CollisionChecker::is_in_sticky_zone,
           py::arg("x"), py::arg("y"),
           "Check if coordinates are in sticky zone")
      .def("check_path_conflict", &CollisionChecker::check_path_conflict,
           py::arg("robot_id"), py::arg("target_x"), py::arg("target_y"),
           py::arg("fleet_positions"), py::arg("fleet_targets"),
           "Check if target conflicts with other robots")
      .def("is_in_bounds", &CollisionChecker::is_in_bounds, py::arg("x"),
           py::arg("y"), "Check if coordinates are within grid")
      .def("check_waypoints", &CollisionChecker::check_waypoints,
           py::arg("waypoints"), "Batch check waypoints against sticky zone")
      .def("find_first_sticky_waypoint",
           &CollisionChecker::find_first_sticky_waypoint, py::arg("waypoints"),
           "Find index of first waypoint in sticky zone, or -1")
      .def("distance_to_sticky_zone",
           &CollisionChecker::distance_to_sticky_zone, py::arg("x"),
           py::arg("y"), "Distance to sticky zone (negative if inside)")

      // Static methods
      .def_static("distance", &CollisionChecker::distance, py::arg("x1"),
                  py::arg("y1"), py::arg("x2"), py::arg("y2"),
                  "Euclidean distance between two points")
      .def_static("manhattan_distance", &CollisionChecker::manhattan_distance,
                  py::arg("x1"), py::arg("y1"), py::arg("x2"), py::arg("y2"),
                  "Manhattan distance between two points");

  // =========================================================================
  // Path Smoothing Functions
  // =========================================================================

  m.def("smooth_path", &smooth_path, py::arg("waypoints"),
        py::arg("points_per_segment") = 10,
        R"doc(
              Smooth path using Catmull-Rom spline interpolation.
              
              Args:
                  waypoints: List of [x, y] coordinates
                  points_per_segment: Interpolation points between waypoints
              
              Returns:
                  Smoothed path with additional interpolated points
          )doc");

  m.def("bezier_smooth", &bezier_smooth, py::arg("waypoints"),
        py::arg("tension") = 0.5, "Smooth path using Bezier curves");

  m.def("moving_average_smooth", &moving_average_smooth, py::arg("waypoints"),
        py::arg("window_size") = 3, "Smooth path using moving average filter");

  m.def("path_length", &path_length, py::arg("waypoints"),
        "Calculate total path length in meters");

  m.def("resample_path", &resample_path, py::arg("waypoints"),
        py::arg("target_spacing") = 0.5,
        "Resample path to have uniform point spacing");

  m.def("is_sharp_turn", &is_sharp_turn, py::arg("p1"), py::arg("p2"),
        py::arg("p3"), py::arg("threshold") = M_PI / 4.0,
        "Check if path makes a sharp turn at p2");

  // =========================================================================
  // Module Info
  // =========================================================================

  m.attr("__version__") = "1.0.0";
  m.attr("__author__") = "Rugved Raote";

#ifdef HAS_ROS2
  m.attr("HAS_ROS2") = true;
#else
  m.attr("HAS_ROS2") = false;
#endif
}
