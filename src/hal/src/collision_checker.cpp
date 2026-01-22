/**
 * @file collision_checker.cpp
 * @brief Implementation of CollisionChecker class
 *
 * @author Rugved Raote
 * @copyright 2025 AgentFleet Project
 */

#include "collision_checker.hpp"
#include <algorithm>
#include <limits>

namespace agentfleet {

// =============================================================================
// Configuration
// =============================================================================

void CollisionChecker::set_grid_size(int width, int height) {
  grid_.width = width;
  grid_.height = height;
}

void CollisionChecker::set_sticky_zone(int x_min, int x_max, int y_min,
                                       int y_max) {
  sticky_zone_.x_min = x_min;
  sticky_zone_.x_max = x_max;
  sticky_zone_.y_min = y_min;
  sticky_zone_.y_max = y_max;
}

// =============================================================================
// Collision Detection
// =============================================================================

bool CollisionChecker::is_in_sticky_zone(double x, double y) const {
  return sticky_zone_.contains(x, y);
}

bool CollisionChecker::check_path_conflict(
    const std::string &robot_id, double target_x, double target_y,
    const std::map<std::string, std::array<double, 2>> &fleet_positions,
    const std::map<std::string, std::array<double, 2>> &fleet_targets) const {
  // Convert target to grid coordinates
  int tx = to_grid(target_x);
  int ty = to_grid(target_y);

  // Check against all other robots
  for (const auto &[other_id, pos] : fleet_positions) {
    if (other_id == robot_id) {
      continue;
    }

    // Conflict 1: Another robot is at the target position
    int ox = to_grid(pos[0]);
    int oy = to_grid(pos[1]);

    if (ox == tx && oy == ty) {
      return true;
    }

    // Conflict 2: Another robot is heading to the same target
    auto target_it = fleet_targets.find(other_id);
    if (target_it != fleet_targets.end()) {
      int otx = to_grid(target_it->second[0]);
      int oty = to_grid(target_it->second[1]);

      if (otx == tx && oty == ty) {
        return true;
      }
    }
  }

  return false;
}

bool CollisionChecker::is_in_bounds(double x, double y) const {
  return x >= 0 && x < grid_.width && y >= 0 && y < grid_.height;
}

std::vector<bool> CollisionChecker::check_waypoints(
    const std::vector<std::array<double, 2>> &waypoints) const {
  std::vector<bool> results;
  results.reserve(waypoints.size());

  for (const auto &wp : waypoints) {
    results.push_back(is_in_sticky_zone(wp[0], wp[1]));
  }

  return results;
}

int CollisionChecker::find_first_sticky_waypoint(
    const std::vector<std::array<double, 2>> &waypoints) const {
  for (size_t i = 0; i < waypoints.size(); ++i) {
    if (is_in_sticky_zone(waypoints[i][0], waypoints[i][1])) {
      return static_cast<int>(i);
    }
  }
  return -1;
}

double CollisionChecker::distance_to_sticky_zone(double x, double y) const {
  // If inside, return negative distance
  if (is_in_sticky_zone(x, y)) {
    // Find distance to nearest edge (negative)
    double dx_min = x - sticky_zone_.x_min;
    double dx_max = sticky_zone_.x_max - x;
    double dy_min = y - sticky_zone_.y_min;
    double dy_max = sticky_zone_.y_max - y;

    double min_dist = std::min({dx_min, dx_max, dy_min, dy_max});
    return -min_dist;
  }

  // Outside - find distance to nearest edge
  double dx = 0.0;
  double dy = 0.0;

  if (x < sticky_zone_.x_min) {
    dx = sticky_zone_.x_min - x;
  } else if (x > sticky_zone_.x_max) {
    dx = x - sticky_zone_.x_max;
  }

  if (y < sticky_zone_.y_min) {
    dy = sticky_zone_.y_min - y;
  } else if (y > sticky_zone_.y_max) {
    dy = y - sticky_zone_.y_max;
  }

  return std::sqrt(dx * dx + dy * dy);
}

} // namespace agentfleet
