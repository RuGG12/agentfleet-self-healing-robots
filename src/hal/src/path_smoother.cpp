/**
 * @file path_smoother.cpp
 * @brief Implementation of path smoothing algorithms
 *
 * @author Rugved Raote
 * @copyright 2025 AgentFleet Project
 */

#include "path_smoother.hpp"
#include <algorithm>
#include <stdexcept>

namespace agentfleet {

// =============================================================================
// Catmull-Rom Spline Interpolation
// =============================================================================

std::vector<std::array<double, 2>>
smooth_path(const std::vector<std::array<double, 2>> &waypoints,
            int points_per_segment) {
  if (waypoints.size() < 2) {
    return waypoints;
  }

  if (waypoints.size() == 2) {
    // Linear interpolation for two points
    std::vector<std::array<double, 2>> result;
    result.reserve(points_per_segment + 1);

    for (int i = 0; i <= points_per_segment; ++i) {
      double t = static_cast<double>(i) / points_per_segment;
      result.push_back(
          {waypoints[0][0] + t * (waypoints[1][0] - waypoints[0][0]),
           waypoints[0][1] + t * (waypoints[1][1] - waypoints[0][1])});
    }
    return result;
  }

  std::vector<std::array<double, 2>> result;
  result.reserve((waypoints.size() - 1) * points_per_segment + 1);

  // Catmull-Rom spline interpolation
  for (size_t i = 0; i < waypoints.size() - 1; ++i) {
    // Get 4 control points (with clamping at boundaries)
    const auto &p0 = (i == 0) ? waypoints[0] : waypoints[i - 1];
    const auto &p1 = waypoints[i];
    const auto &p2 = waypoints[i + 1];
    const auto &p3 =
        (i == waypoints.size() - 2) ? waypoints[i + 1] : waypoints[i + 2];

    // Interpolate segment
    for (int j = 0; j < points_per_segment; ++j) {
      double t = static_cast<double>(j) / points_per_segment;
      double t2 = t * t;
      double t3 = t2 * t;

      // Catmull-Rom basis functions
      double b0 = -0.5 * t3 + t2 - 0.5 * t;
      double b1 = 1.5 * t3 - 2.5 * t2 + 1.0;
      double b2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t;
      double b3 = 0.5 * t3 - 0.5 * t2;

      result.push_back({b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                        b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]});
    }
  }

  // Add final point
  result.push_back(waypoints.back());

  return result;
}

// =============================================================================
// Bezier Curve Smoothing
// =============================================================================

std::vector<std::array<double, 2>>
bezier_smooth(const std::vector<std::array<double, 2>> &waypoints,
              double tension) {
  if (waypoints.size() < 3) {
    return waypoints;
  }

  std::vector<std::array<double, 2>> result;
  result.reserve(waypoints.size() * 10);

  // Add first point
  result.push_back(waypoints[0]);

  // Process each segment
  for (size_t i = 1; i < waypoints.size() - 1; ++i) {
    const auto &prev = waypoints[i - 1];
    const auto &curr = waypoints[i];
    const auto &next = waypoints[i + 1];

    // Calculate control points based on tension
    double ctrl1_x = curr[0] - tension * (curr[0] - prev[0]);
    double ctrl1_y = curr[1] - tension * (curr[1] - prev[1]);
    double ctrl2_x = curr[0] + tension * (next[0] - curr[0]);
    double ctrl2_y = curr[1] + tension * (next[1] - curr[1]);

    // Quadratic Bezier interpolation to control point 1
    for (int j = 1; j <= 5; ++j) {
      double t = static_cast<double>(j) / 5.0;
      double x = (1 - t) * (1 - t) * prev[0] + 2 * (1 - t) * t * ctrl1_x +
                 t * t * curr[0];
      double y = (1 - t) * (1 - t) * prev[1] + 2 * (1 - t) * t * ctrl1_y +
                 t * t * curr[1];

      // Avoid duplicates
      if (result.empty() || result.back()[0] != x || result.back()[1] != y) {
        result.push_back({x, y});
      }
    }
  }

  // Add final point
  result.push_back(waypoints.back());

  return result;
}

// =============================================================================
// Moving Average Smoothing
// =============================================================================

std::vector<std::array<double, 2>>
moving_average_smooth(const std::vector<std::array<double, 2>> &waypoints,
                      int window_size) {
  if (waypoints.size() < 3 || window_size < 2) {
    return waypoints;
  }

  std::vector<std::array<double, 2>> result;
  result.reserve(waypoints.size());

  int half_window = window_size / 2;

  for (size_t i = 0; i < waypoints.size(); ++i) {
    double sum_x = 0.0;
    double sum_y = 0.0;
    int count = 0;

    for (int j = -half_window; j <= half_window; ++j) {
      int idx = static_cast<int>(i) + j;
      if (idx >= 0 && idx < static_cast<int>(waypoints.size())) {
        sum_x += waypoints[idx][0];
        sum_y += waypoints[idx][1];
        ++count;
      }
    }

    result.push_back({sum_x / count, sum_y / count});
  }

  // Preserve start and end points exactly
  result[0] = waypoints[0];
  result[result.size() - 1] = waypoints.back();

  return result;
}

// =============================================================================
// Utility Functions
// =============================================================================

double path_length(const std::vector<std::array<double, 2>> &waypoints) {
  if (waypoints.size() < 2) {
    return 0.0;
  }

  double length = 0.0;
  for (size_t i = 1; i < waypoints.size(); ++i) {
    double dx = waypoints[i][0] - waypoints[i - 1][0];
    double dy = waypoints[i][1] - waypoints[i - 1][1];
    length += std::sqrt(dx * dx + dy * dy);
  }

  return length;
}

std::vector<std::array<double, 2>>
resample_path(const std::vector<std::array<double, 2>> &waypoints,
              double target_spacing) {
  if (waypoints.size() < 2) {
    return waypoints;
  }

  double total_length = path_length(waypoints);
  int num_points =
      std::max(2, static_cast<int>(total_length / target_spacing) + 1);

  std::vector<std::array<double, 2>> result;
  result.reserve(num_points);
  result.push_back(waypoints[0]);

  double accumulated = 0.0;
  double next_target = target_spacing;
  size_t segment = 0;

  while (segment < waypoints.size() - 1) {
    double dx = waypoints[segment + 1][0] - waypoints[segment][0];
    double dy = waypoints[segment + 1][1] - waypoints[segment][1];
    double segment_length = std::sqrt(dx * dx + dy * dy);

    while (accumulated + segment_length >= next_target &&
           result.size() < static_cast<size_t>(num_points) - 1) {
      double t = (next_target - accumulated) / segment_length;
      result.push_back(
          {waypoints[segment][0] + t * dx, waypoints[segment][1] + t * dy});
      next_target += target_spacing;
    }

    accumulated += segment_length;
    ++segment;
  }

  // Ensure final point is included
  if (result.back()[0] != waypoints.back()[0] ||
      result.back()[1] != waypoints.back()[1]) {
    result.push_back(waypoints.back());
  }

  return result;
}

bool is_sharp_turn(const std::array<double, 2> &p1,
                   const std::array<double, 2> &p2,
                   const std::array<double, 2> &p3, double threshold) {
  // Vector from p1 to p2
  double v1x = p2[0] - p1[0];
  double v1y = p2[1] - p1[1];

  // Vector from p2 to p3
  double v2x = p3[0] - p2[0];
  double v2y = p3[1] - p2[1];

  // Normalize vectors
  double len1 = std::sqrt(v1x * v1x + v1y * v1y);
  double len2 = std::sqrt(v2x * v2x + v2y * v2y);

  if (len1 < 1e-9 || len2 < 1e-9) {
    return false; // Degenerate case
  }

  v1x /= len1;
  v1y /= len1;
  v2x /= len2;
  v2y /= len2;

  // Calculate angle between vectors
  double dot = v1x * v2x + v1y * v2y;
  dot = std::max(-1.0, std::min(1.0, dot)); // Clamp for numerical stability
  double angle = std::acos(dot);

  return angle > threshold;
}

} // namespace agentfleet
