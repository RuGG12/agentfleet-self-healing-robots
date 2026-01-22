/**
 * @file robot_hal.hpp
 * @brief Hardware Abstraction Layer for AgentFleet robots
 * 
 * Provides low-latency ROS 2 communication via rclcpp with thread-safe
 * state management and fault injection capabilities.
 * 
 * @author Rugved Raote
 * @copyright 2025 AgentFleet Project
 */

#ifndef AGENTFLEET_ROBOT_HAL_HPP
#define AGENTFLEET_ROBOT_HAL_HPP

#include <string>
#include <array>
#include <atomic>
#include <memory>
#include <mutex>
#include <thread>
#include <random>

#ifdef HAS_ROS2
#include <rclcpp/rclcpp.hpp>
#include <geometry_msgs/msg/twist.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#endif

namespace agentfleet {

/**
 * @brief Fault types for hardware failure simulation
 */
enum class FaultState {
    NONE,           ///< No active fault
    MOTOR_TIMEOUT,  ///< Motors unresponsive - blocks cmd_vel
    PACKET_DROP,    ///< Random 50% packet loss
    SENSOR_FREEZE   ///< Odom/scan data stops updating
};

/**
 * @brief Robot status states
 */
enum class RobotStatus {
    IDLE,
    NAVIGATING,
    STUCK,
    RECOVERING,
    FAULT
};

/**
 * @brief Convert RobotStatus to string
 */
inline std::string status_to_string(RobotStatus status) {
    switch (status) {
        case RobotStatus::IDLE: return "IDLE";
        case RobotStatus::NAVIGATING: return "NAVIGATING";
        case RobotStatus::STUCK: return "STUCK";
        case RobotStatus::RECOVERING: return "RECOVERING";
        case RobotStatus::FAULT: return "FAULT";
        default: return "UNKNOWN";
    }
}

/**
 * @brief Hardware Abstraction Layer for a single robot
 * 
 * Provides thread-safe access to robot state and low-latency
 * command publishing. Supports fault injection for testing
 * recovery algorithms.
 * 
 * @code
 * auto hal = std::make_unique<RobotHAL>("robot_1");
 * hal->publish_cmd_vel(0.5, 0.0);  // Move forward
 * auto pose = hal->get_pose();      // Thread-safe state access
 * @endcode
 */
class RobotHAL {
public:
    /**
     * @brief Construct HAL for a specific robot
     * @param robot_id Unique robot identifier (e.g., "robot_1")
     */
    explicit RobotHAL(const std::string& robot_id);
    
    /**
     * @brief Destructor - cleanly shuts down ROS node
     */
    ~RobotHAL();
    
    // Non-copyable, movable
    RobotHAL(const RobotHAL&) = delete;
    RobotHAL& operator=(const RobotHAL&) = delete;
    RobotHAL(RobotHAL&&) = default;
    RobotHAL& operator=(RobotHAL&&) = default;
    
    // =========================================================================
    // Command Publishing
    // =========================================================================
    
    /**
     * @brief Publish velocity command to robot
     * @param linear_x Linear velocity (m/s)
     * @param angular_z Angular velocity (rad/s)
     * @return true if command was published, false if blocked by fault
     */
    bool publish_cmd_vel(double linear_x, double angular_z);
    
    /**
     * @brief Stop the robot immediately
     */
    void stop();
    
    // =========================================================================
    // State Getters (Thread-Safe)
    // =========================================================================
    
    /**
     * @brief Get current robot position
     * @return Array of [x, y] in meters
     */
    std::array<double, 2> get_pose() const;
    
    /**
     * @brief Get current robot yaw angle
     * @return Yaw in radians (-pi to pi)
     */
    double get_yaw() const;
    
    /**
     * @brief Get robot operational status
     * @return Status as string ("IDLE", "NAVIGATING", etc.)
     */
    std::string get_status() const;
    
    /**
     * @brief Get robot ID
     */
    const std::string& get_robot_id() const { return robot_id_; }
    
    /**
     * @brief Check if HAL is connected to ROS
     */
    bool is_connected() const;
    
    // =========================================================================
    // Status Management
    // =========================================================================
    
    /**
     * @brief Set robot operational status
     * @param status New status value
     */
    void set_status(RobotStatus status);
    
    /**
     * @brief Set target position for navigation
     * @param x Target X coordinate
     * @param y Target Y coordinate
     */
    void set_target(double x, double y);
    
    /**
     * @brief Get current target position
     * @return Array of [x, y] target coordinates
     */
    std::array<double, 2> get_target() const;
    
    // =========================================================================
    // Fault Injection (Testing)
    // =========================================================================
    
    /**
     * @brief Inject a simulated hardware fault
     * @param fault_type Fault type: "motor_timeout", "packet_drop", "sensor_freeze"
     */
    void inject_fault(const std::string& fault_type);
    
    /**
     * @brief Clear all active faults
     */
    void clear_faults();
    
    /**
     * @brief Get current fault state
     */
    FaultState get_fault_state() const;
    
    /**
     * @brief Check if any fault is active
     */
    bool has_fault() const { return fault_state_.load() != FaultState::NONE; }

private:
    std::string robot_id_;
    
    // Thread-safe state using atomics
    std::atomic<double> pose_x_{0.0};
    std::atomic<double> pose_y_{0.0};
    std::atomic<double> yaw_{0.0};
    std::atomic<double> target_x_{0.0};
    std::atomic<double> target_y_{0.0};
    std::atomic<RobotStatus> status_{RobotStatus::IDLE};
    std::atomic<FaultState> fault_state_{FaultState::NONE};
    std::atomic<bool> connected_{false};
    
    // Random number generator for packet drop simulation
    mutable std::mt19937 rng_{std::random_device{}()};
    mutable std::uniform_real_distribution<> drop_dist_{0.0, 1.0};
    
#ifdef HAS_ROS2
    // ROS 2 node and communication
    std::shared_ptr<rclcpp::Node> node_;
    rclcpp::Publisher<geometry_msgs::msg::Twist>::SharedPtr cmd_vel_pub_;
    rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
    rclcpp::Subscription<sensor_msgs::msg::LaserScan>::SharedPtr scan_sub_;
    
    std::unique_ptr<std::thread> spin_thread_;
    std::atomic<bool> shutdown_{false};
    
    // Callback handlers
    void odom_callback(const nav_msgs::msg::Odometry::SharedPtr msg);
    void scan_callback(const sensor_msgs::msg::LaserScan::SharedPtr msg);
    
    // ROS initialization
    void init_ros();
    void spin_ros();
#endif
};

} // namespace agentfleet

#endif // AGENTFLEET_ROBOT_HAL_HPP
