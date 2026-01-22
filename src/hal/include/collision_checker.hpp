/**
 * @file collision_checker.hpp
 * @brief Fast 2D grid-based collision checking for AgentFleet
 *
 * Provides efficient collision detection for robot path planning,
 * including sticky zone detection and fleet conflict resolution.
 *
 * @author Rugved Raote
 * @copyright 2025 AgentFleet Project
 */

#ifndef AGENTFLEET_COLLISION_CHECKER_HPP
#define AGENTFLEET_COLLISION_CHECKER_HPP

#include <array>
#include <cmath>
#include <map>
#include <string>
#include <vector>


namespace agentfleet {

/**
 * @brief Sticky zone definition (hazard area)
 */
struct StickyZone {
  int x_min = 5;
  int x_max = 7;
  int y_min = 5;
  int y_max = 7;

  bool contains(double x, double y) const {
    return x >= x_min && x <= x_max && y >= y_min && y <= y_max;
  }
};

/**
 * @brief Grid configuration
 */
struct GridConfig {
  int width = 10;
  int height = 10;
  double cell_size = 1.0; // meters per cell
};

/**
 * @brief Fast collision checker for 2D grid environments
 *
 * Optimized for high-frequency collision checks during navigation.
 * Uses integer grid coordinates for fast lookups.
 *
 * @code
 * CollisionChecker checker;
 * checker.set_sticky_zone(5, 7, 5, 7);
 *
 * if (checker.is_in_sticky_zone(6.0, 6.0)) {
 *     // Robot in danger zone
 * }
 * @endcode
 */
class CollisionChecker {
public:
  CollisionChecker() = default;
  ~CollisionChecker() = default;

  // =========================================================================
  // Configuration
  // =========================================================================

  /**
   * @brief Set grid dimensions
   * @param width Grid width in cells
   * @param height Grid height in cells
   */
  void set_grid_size(int width, int height);

  /**
   * @brief Set sticky zone bounds
   * @param x_min Minimum X coordinate
   * @param x_max Maximum X coordinate
   * @param y_min Minimum Y coordinate
   * @param y_max Maximum Y coordinate
   */
  void set_sticky_zone(int x_min, int x_max, int y_min, int y_max);

  /**
   * @brief Get current grid configuration
   */
  const GridConfig &get_grid_config() const { return grid_; }

  /**
   * @brief Get current sticky zone configuration
   */
  const StickyZone &get_sticky_zone() const { return sticky_zone_; }

  // =========================================================================
  // Collision Detection
  // =========================================================================

  /**
   * @brief Check if coordinates are within the sticky zone
   * @param x X coordinate (meters)
   * @param y Y coordinate (meters)
   * @return true if in sticky zone
   */
  bool is_in_sticky_zone(double x, double y) const;

  /**
   * @brief Check if target conflicts with other robots
   * @param robot_id ID of the robot planning the move
   * @param target_x Target X coordinate
   * @param target_y Target Y coordinate
   * @param fleet_positions Map of robot_id -> [x, y] positions
   * @param fleet_targets Map of robot_id -> [x, y] targets
   * @return true if conflict exists
   */
  bool check_path_conflict(
      const std::string &robot_id, double target_x, double target_y,
      const std::map<std::string, std::array<double, 2>> &fleet_positions,
      const std::map<std::string, std::array<double, 2>> &fleet_targets) const;

  /**
   * @brief Check if coordinates are within grid bounds
   * @param x X coordinate
   * @param y Y coordinate
   * @return true if within bounds
   */
  bool is_in_bounds(double x, double y) const;

  /**
   * @brief Batch check multiple waypoints against sticky zone
   *
   * Optimized for checking entire paths at once.
   *
   * @param waypoints Vector of [x, y] coordinates
   * @return Vector of bools (true = in sticky zone)
   */
  std::vector<bool>
  check_waypoints(const std::vector<std::array<double, 2>> &waypoints) const;

  /**
   * @brief Find first waypoint that enters sticky zone
   * @param waypoints Vector of [x, y] coordinates
   * @return Index of first sticky waypoint, or -1 if none
   */
  int find_first_sticky_waypoint(
      const std::vector<std::array<double, 2>> &waypoints) const;

  // =========================================================================
  // Distance Calculations
  // =========================================================================

  /**
   * @brief Calculate Euclidean distance between two points
   */
  static double distance(double x1, double y1, double x2, double y2) {
    double dx = x2 - x1;
    double dy = y2 - y1;
    return std::sqrt(dx * dx + dy * dy);
  }

  /**
   * @brief Calculate Manhattan distance between two points
   */
  static int manhattan_distance(int x1, int y1, int x2, int y2) {
    return std::abs(x2 - x1) + std::abs(y2 - y1);
  }

  /**
   * @brief Calculate distance to nearest sticky zone edge
   * @param x X coordinate
   * @param y Y coordinate
   * @return Distance (positive = outside, negative = inside)
   */
  double distance_to_sticky_zone(double x, double y) const;

private:
  GridConfig grid_;
  StickyZone sticky_zone_;

  // Helper to round coordinates to grid cells
  static int to_grid(double coord) {
    return static_cast<int>(std::round(coord));
  }
};

} // namespace agentfleet

#endif // AGENTFLEET_COLLISION_CHECKER_HPP
