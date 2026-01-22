/**
 * @file robot_hal.cpp
 * @brief Implementation of RobotHAL class
 *
 * @author Rugved Raote
 * @copyright 2025 AgentFleet Project
 */

#include "robot_hal.hpp"
#include <chrono>
#include <iostream>


namespace agentfleet {

// =============================================================================
// Constructor / Destructor
// =============================================================================

RobotHAL::RobotHAL(const std::string &robot_id) : robot_id_(robot_id) {
  std::cout << "[HAL] Initializing RobotHAL for " << robot_id << std::endl;

#ifdef HAS_ROS2
  init_ros();
#else
  std::cout << "[HAL] Running in standalone mode (no ROS 2)" << std::endl;
  connected_.store(true); // Simulate connection in standalone mode
#endif
}

RobotHAL::~RobotHAL() {
  std::cout << "[HAL] Shutting down RobotHAL for " << robot_id_ << std::endl;

#ifdef HAS_ROS2
  shutdown_.store(true);
  if (spin_thread_ && spin_thread_->joinable()) {
    spin_thread_->join();
  }
#endif
}

// =============================================================================
// ROS 2 Initialization (Conditional Compilation)
// =============================================================================

#ifdef HAS_ROS2

void RobotHAL::init_ros() {
  // Initialize ROS if not already done
  if (!rclcpp::ok()) {
    rclcpp::init(0, nullptr);
  }

  // Create node with unique name
  std::string node_name = "hal_" + robot_id_;
  node_ = std::make_shared<rclcpp::Node>(node_name);

  // Quality of Service settings for real-time performance
  auto qos = rclcpp::QoS(10)
                 .reliability(rclcpp::ReliabilityPolicy::BestEffort)
                 .durability(rclcpp::DurabilityPolicy::Volatile);

  // Create publisher for velocity commands
  std::string cmd_vel_topic = "/" + robot_id_ + "/cmd_vel";
  cmd_vel_pub_ =
      node_->create_publisher<geometry_msgs::msg::Twist>(cmd_vel_topic, qos);

  // Create subscriber for odometry
  std::string odom_topic = "/" + robot_id_ + "/odom";
  odom_sub_ = node_->create_subscription<nav_msgs::msg::Odometry>(
      odom_topic, qos, [this](const nav_msgs::msg::Odometry::SharedPtr msg) {
        this->odom_callback(msg);
      });

  // Create subscriber for laser scan
  std::string scan_topic = "/" + robot_id_ + "/scan";
  scan_sub_ = node_->create_subscription<sensor_msgs::msg::LaserScan>(
      scan_topic, qos,
      [this](const sensor_msgs::msg::LaserScan::SharedPtr msg) {
        this->scan_callback(msg);
      });

  std::cout << "[HAL] ROS 2 topics:" << std::endl;
  std::cout << "  - Publisher:  " << cmd_vel_topic << std::endl;
  std::cout << "  - Subscriber: " << odom_topic << std::endl;
  std::cout << "  - Subscriber: " << scan_topic << std::endl;

  // Start spin thread
  spin_thread_ = std::make_unique<std::thread>(&RobotHAL::spin_ros, this);

  connected_.store(true);
}

void RobotHAL::spin_ros() {
  while (!shutdown_.load() && rclcpp::ok()) {
    rclcpp::spin_some(node_);
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
}

void RobotHAL::odom_callback(const nav_msgs::msg::Odometry::SharedPtr msg) {
  // Check for sensor freeze fault
  if (fault_state_.load() == FaultState::SENSOR_FREEZE) {
    return; // Don't update state
  }

  // Extract position atomically
  pose_x_.store(msg->pose.pose.position.x);
  pose_y_.store(msg->pose.pose.position.y);

  // Extract yaw from quaternion
  const auto &q = msg->pose.pose.orientation;
  double siny_cosp = 2.0 * (q.w * q.z + q.x * q.y);
  double cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z);
  yaw_.store(std::atan2(siny_cosp, cosy_cosp));
}

void RobotHAL::scan_callback(const sensor_msgs::msg::LaserScan::SharedPtr msg) {
  // Check for sensor freeze fault
  if (fault_state_.load() == FaultState::SENSOR_FREEZE) {
    return;
  }

  // Store scan data if needed for obstacle detection
  // (Currently not implemented - placeholder for future use)
  (void)msg;
}

#endif // HAS_ROS2

// =============================================================================
// Command Publishing
// =============================================================================

bool RobotHAL::publish_cmd_vel(double linear_x, double angular_z) {
  // Check for faults
  FaultState fault = fault_state_.load();

  if (fault == FaultState::MOTOR_TIMEOUT) {
    std::cout << "[HAL] FAULT: Motor timeout - command blocked" << std::endl;
    return false;
  }

  if (fault == FaultState::PACKET_DROP) {
    // 50% chance of dropping the packet
    if (drop_dist_(rng_) < 0.5) {
      std::cout << "[HAL] FAULT: Packet dropped" << std::endl;
      return false;
    }
  }

#ifdef HAS_ROS2
  if (!cmd_vel_pub_) {
    return false;
  }

  auto msg = geometry_msgs::msg::Twist();
  msg.linear.x = linear_x;
  msg.angular.z = angular_z;
  cmd_vel_pub_->publish(msg);
  return true;
#else
  // Standalone mode - just log the command
  std::cout << "[HAL] cmd_vel(" << robot_id_ << "): linear=" << linear_x
            << ", angular=" << angular_z << std::endl;
  return true;
#endif
}

void RobotHAL::stop() { publish_cmd_vel(0.0, 0.0); }

// =============================================================================
// State Getters
// =============================================================================

std::array<double, 2> RobotHAL::get_pose() const {
  return {pose_x_.load(), pose_y_.load()};
}

double RobotHAL::get_yaw() const { return yaw_.load(); }

std::string RobotHAL::get_status() const {
  return status_to_string(status_.load());
}

bool RobotHAL::is_connected() const { return connected_.load(); }

// =============================================================================
// Status Management
// =============================================================================

void RobotHAL::set_status(RobotStatus status) { status_.store(status); }

void RobotHAL::set_target(double x, double y) {
  target_x_.store(x);
  target_y_.store(y);
}

std::array<double, 2> RobotHAL::get_target() const {
  return {target_x_.load(), target_y_.load()};
}

// =============================================================================
// Fault Injection
// =============================================================================

void RobotHAL::inject_fault(const std::string &fault_type) {
  std::cout << "[HAL] Injecting fault: " << fault_type << " on " << robot_id_
            << std::endl;

  if (fault_type == "motor_timeout" || fault_type == "MOTOR_TIMEOUT") {
    fault_state_.store(FaultState::MOTOR_TIMEOUT);
    status_.store(RobotStatus::FAULT);
  } else if (fault_type == "packet_drop" || fault_type == "PACKET_DROP") {
    fault_state_.store(FaultState::PACKET_DROP);
  } else if (fault_type == "sensor_freeze" || fault_type == "SENSOR_FREEZE") {
    fault_state_.store(FaultState::SENSOR_FREEZE);
  } else {
    std::cout << "[HAL] Unknown fault type: " << fault_type << std::endl;
  }
}

void RobotHAL::clear_faults() {
  std::cout << "[HAL] Clearing faults on " << robot_id_ << std::endl;
  fault_state_.store(FaultState::NONE);

  // Reset status if it was FAULT
  if (status_.load() == RobotStatus::FAULT) {
    status_.store(RobotStatus::IDLE);
  }
}

FaultState RobotHAL::get_fault_state() const { return fault_state_.load(); }

} // namespace agentfleet
