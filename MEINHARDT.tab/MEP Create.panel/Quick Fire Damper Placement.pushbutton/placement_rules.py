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


def classify_instance_status(
    exists,
    is_valid,
    is_family_instance,
    is_accessory,
    hosted_on_duct,
    connected_to_duct,
):
    if not exists:
        return "missing"
    if not is_valid:
        return "invalid"
    if not is_family_instance:
        return "not-family-instance"
    if not is_accessory:
        return "wrong-category"
    if hosted_on_duct:
        return "hosted"
    if connected_to_duct:
        return "connected"
    return "detached"


def bounded_curve_candidates(
    point_at_distance,
    segment_start_distance,
    segment_end_distance,
    curve_length,
    obstacle_points,
    clearance_feet,
    max_distance_feet,
    step_distance_feet,
):
    length = float(curve_length)
    clearance = float(clearance_feet)
    max_distance = float(max_distance_feet)
    step_distance = float(step_distance_feet)
    values = (length, clearance, max_distance, step_distance)
    if any(math.isnan(value) or math.isinf(value) for value in values):
        raise ValueError("Curve candidate distances must be finite")
    if length <= 0 or clearance < 0 or max_distance < 0 or step_distance <= 0:
        raise ValueError("Curve candidate distances must be non-negative and bounded")

    start = min(max(float(segment_start_distance), 0.0), length)
    end = min(max(float(segment_end_distance), 0.0), length)
    if start > end:
        start, end = end, start
    obstacles = [tuple(float(value) for value in point) for point in obstacle_points]
    if not obstacles or max_distance == 0:
        return []

    offsets = []
    offset = step_distance
    while offset < max_distance:
        offsets.append(offset)
        offset += step_distance
    offsets.append(max_distance)

    candidates = []
    seen = []
    for offset in offsets:
        for boundary, direction in ((start, -1.0), (end, 1.0)):
            distance = boundary + direction * offset
            if distance < 0.0 or distance > length:
                continue
            point = tuple(float(value) for value in point_at_distance(distance))
            boundary_point = tuple(float(value) for value in point_at_distance(boundary))
            distances_from_boundary = [
                _distance_squared(boundary_point, obstacle) for obstacle in obstacles
            ]
            distances_from_candidate = [
                _distance_squared(point, obstacle) for obstacle in obstacles
            ]
            clearance_squared = clearance * clearance
            if any(distance_squared < clearance_squared for distance_squared in distances_from_candidate):
                continue
            if any(
                candidate_distance + 1e-12 < boundary_distance
                for candidate_distance, boundary_distance in zip(
                    distances_from_candidate, distances_from_boundary
                )
            ):
                continue
            if not any(
                candidate_distance > boundary_distance + 1e-12
                for candidate_distance, boundary_distance in zip(
                    distances_from_candidate, distances_from_boundary
                )
            ):
                continue
            if any(_distance_squared(point, existing) <= 1e-12 for existing in seen):
                continue
            seen.append(point)
            candidates.append((point, offset))
    return candidates


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
