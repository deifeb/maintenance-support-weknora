from threading import Lock

TaskKey = tuple[str, int]


class TaskRegistry:
    def __init__(self) -> None:
        self._running: set[TaskKey] = set()
        self._lock = Lock()

    def register(self, key: TaskKey) -> bool:
        with self._lock:
            if key in self._running:
                return False
            self._running.add(key)
            return True

    def unregister(self, key: TaskKey) -> None:
        with self._lock:
            self._running.discard(key)

    def is_running(self, key: TaskKey) -> bool:
        with self._lock:
            return key in self._running


registry = TaskRegistry()
group_registry = TaskRegistry()
reservation_expiry_registry = TaskRegistry()
