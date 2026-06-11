def clamp(value: int, min_value: int, max_value: int) -> int:
    return max(min_value, min(max_value, value))
