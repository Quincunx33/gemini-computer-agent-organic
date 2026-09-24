import time
import threading

class MetricsCollector:
    """
    Tracks operational metrics for the task queue system:
    - Throughput (tasks/sec)
    - Success and failure counts
    - Execution latency (avg, min, max) in seconds
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.success_count = 0
        self.failure_count = 0
        self.retry_count = 0
        self.total_execution_time = 0.0
        self.min_latency = float('inf')
        self.max_latency = 0.0
        self.start_time = time.time()
        self.latencies = []

    def record_success(self, latency: float):
        with self._lock:
            self.success_count += 1
            self.total_execution_time += latency
            self.latencies.append(latency)
            if latency < self.min_latency:
                self.min_latency = latency
            if latency > self.max_latency:
                self.max_latency = latency

    def record_failure(self):
        with self._lock:
            self.failure_count += 1

    def record_retry(self):
        with self._lock:
            self.retry_count += 1

    def get_metrics(self) -> dict:
        with self._lock:
            uptime = max(0.001, time.time() - self.start_time)
            total_processed = self.success_count + self.failure_count
            throughput = total_processed / uptime
            avg_latency = (self.total_execution_time / self.success_count) if self.success_count > 0 else 0.0
            min_lat = self.min_latency if self.success_count > 0 else 0.0
            max_lat = self.max_latency if self.success_count > 0 else 0.0

            return {
                "uptime_seconds": round(uptime, 2),
                "total_processed": total_processed,
                "success_count": self.success_count,
                "failure_count": self.failure_count,
                "retry_count": self.retry_count,
                "throughput_tasks_per_sec": round(throughput, 4),
                "latency_avg_seconds": round(avg_latency, 4),
                "latency_min_seconds": round(min_lat, 4),
                "latency_max_seconds": round(max_lat, 4)
            }
