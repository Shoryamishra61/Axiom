from datetime import datetime, timezone
from types import SimpleNamespace

from api.metrics_routes import _throughput_series


def test_throughput_fills_idle_hours_and_preserves_counts():
    start = datetime(2026, 7, 3, 0, tzinfo=timezone.utc)
    rows = [SimpleNamespace(bucket=start, completed=2, failed=1)]
    series = _throughput_series(rows, start)

    assert len(series) == 12
    assert series[0]["completed"] == 2 and series[0]["failed"] == 1
    assert all(point["completed"] == point["failed"] == 0 for point in series[1:])
