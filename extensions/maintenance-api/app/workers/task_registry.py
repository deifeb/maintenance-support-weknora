from threading import Lock


class TaskRegistry:
    def __init__(self) -> None:
        self._running: set[int] = set()
        self._lock = Lock()

    def register(self, calculation_id: int) -> bool:
        with self._lock:
            if calculation_id in self._running:
                return False
            self._running.add(calculation_id)
            return True

    def unregister(self, calculation_id: int) -> None:
        with self._lock:
            self._running.discard(calculation_id)

    def is_running(self, calculation_id: int) -> bool:
        with self._lock:
            return calculation_id in self._running


registry = TaskRegistry()
