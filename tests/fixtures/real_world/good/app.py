"""Production-grade Python service module."""


def calculate_metrics(count: int, duration_seconds: float) -> float:
    """Calculate rate of operations per second."""
    if duration_seconds <= 0:
        return 0.0
    return round(count / duration_seconds, 2)


if __name__ == "__main__":
    rate = calculate_metrics(100, 5.0)
    print(f"Rate: {rate} ops/sec")
