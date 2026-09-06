from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from worker import network_failure_means_closed


def test_http_failures_are_not_closure():
    assert network_failure_means_closed(429, False) is False
    assert network_failure_means_closed(404, False) is False
    assert network_failure_means_closed(None, True) is False


if __name__ == "__main__":
    test_http_failures_are_not_closure()
    print("ok")
