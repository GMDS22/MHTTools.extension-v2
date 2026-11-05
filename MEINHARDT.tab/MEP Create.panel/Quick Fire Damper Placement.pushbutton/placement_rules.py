import math


MM_PER_FOOT = 304.8
DEFAULT_DUPLICATE_RADIUS_MM = 200.0
DEFAULT_ELBOW_CLEARANCE_MM = 300.0


def millimeters_to_feet(value):
    radius_mm = float(value)
    if radius_mm <= 0 or math.isnan(radius_mm) or math.isinf(radius_mm):
        raise ValueError("Duplicate radius must be a positive finite number of millimeters")
    return radius_mm / MM_PER_FOOT


def points_within_radius(first, second, radius_feet):
    dx = float(first[0]) - float(second[0])
    dy = float(first[1]) - float(second[1])
    dz = float(first[2]) - float(second[2])
    radius = float(radius_feet)
    return dx * dx + dy * dy + dz * dz <= radius * radius


def closest_clear_point(candidate_points, obstacle_points, clearance_feet):
    candidates = [tuple(float(value) for value in point) for point in candidate_points]
    obstacles = [tuple(float(value) for value in point) for point in obstacle_points]
    clearance = float(clearance_feet)
    if clearance < 0 or math.isnan(clearance) or math.isinf(clearance):
        raise ValueError("Clearance must be a non-negative finite number of feet")
    if not candidates:
        return None

    midpoint_index = (len(candidates) - 1) / 2.0
    safe_candidates = []
    for index, candidate in enumerate(candidates):
        if all(not points_within_radius(candidate, obstacle, clearance) for obstacle in obstacles):
            safe_candidates.append((abs(index - midpoint_index), candidate))
    return min(safe_candidates, key=lambda item: item[0])[1] if safe_candidates else None


def adjust_point_away_from_points(segment_start, segment_end, obstacle_points, clearance_feet):
    start = tuple(float(value) for value in segment_start)
    end = tuple(float(value) for value in segment_end)
    direction = tuple(end[index] - start[index] for index in range(3))
    length_squared = sum(value * value for value in direction)
    clearance = float(clearance_feet)
    if clearance < 0 or math.isnan(clearance) or math.isinf(clearance):
        raise ValueError("Clearance must be a non-negative finite number of feet")
    if length_squared == 0:
        return start if all(_distance_squared(start, point) >= clearance * clearance for point in obstacle_points) else None

    safe_intervals = [(0.0, 1.0)]
    clearance_squared = clearance * clearance
    for obstacle in obstacle_points:
        offset = tuple(start[index] - float(obstacle[index]) for index in range(3))
        projection = sum(offset[index] * direction[index] for index in range(3))
        constant = sum(value * value for value in offset) - clearance_squared
        discriminant = projection * projection - length_squared * constant
        if discriminant <= 0:
            midpoint = tuple(start[index] + 0.5 * direction[index] for index in range(3))
            if discriminant < 0 and points_within_radius(midpoint, obstacle, clearance):
                return None
            continue

        root = math.sqrt(discriminant)
        forbidden_start = (-projection - root) / length_squared
        forbidden_end = (-projection + root) / length_squared
        remaining = []
        for interval_start, interval_end in safe_intervals:
            if forbidden_end <= interval_start or forbidden_start >= interval_end:
                remaining.append((interval_start, interval_end))
                continue
            if forbidden_start >= interval_start:
                remaining.append((interval_start, min(interval_end, forbidden_start)))
            if forbidden_end <= interval_end:
                remaining.append((max(interval_start, forbidden_end), interval_end))
        safe_intervals = [interval for interval in remaining if interval[0] <= interval[1]]
        if not safe_intervals:
            return None

    candidates = []
    for interval_start, interval_end in safe_intervals:
        parameter = min(max(0.5, interval_start), interval_end)
        point = tuple(start[index] + parameter * direction[index] for index in range(3))
        if all(_distance_squared(point, obstacle) >= clearance_squared for obstacle in obstacle_points):
            candidates.append((abs(parameter - 0.5), point))
    return min(candidates, key=lambda candidate: candidate[0])[1] if candidates else None


def _distance_squared(first, second):
    return sum((float(first[index]) - float(second[index])) ** 2 for index in range(3))