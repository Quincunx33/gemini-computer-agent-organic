import time
import json
import math
import random
from queue_engine import QueueEngine, TaskState
from metrics_collector import MetricsCollector

def run_benchmark(total_tasks: int = 50, max_workers: int = 4, db_path: str = "benchmark_queue.db"):
    print(f"[*] Starting Distributed Task Queue Benchmark ({total_tasks} tasks, {max_workers} worker threads)...")
    collector = MetricsCollector()
    engine = QueueEngine(db_path=db_path, max_workers=max_workers, metrics_collector=collector)

    # Workload handlers
    def fast_calc(p):
        return sum(i * i for i in range(p.get("n", 1000)))

    def io_simulation(p):
        time.sleep(p.get("delay", 0.005))
        return {"status": "io_finished", "size": p.get("size", 1024)}

    flaky_state = {}
    def transient_worker(p):
        tid = p.get("tid", "def")
        flaky_state[tid] = flaky_state.get(tid, 0) + 1
        if flaky_state[tid] < 2:
            raise RuntimeError("Transient network glitch")
        return {"recovered_at_attempt": flaky_state[tid]}

    engine.register_handler("fast_calc", fast_calc)
    engine.register_handler("io_simulation", io_simulation)
    engine.register_handler("transient_worker", transient_worker)

    engine.start()
    t_start = time.time()

    # Enqueue mixed tasks with varied priorities
    task_ids = []
    for i in range(total_tasks):
        mod = i % 3
        priority = random.randint(-5, 10)
        if mod == 0:
            t = engine.submit_task("fast_calc", {"n": 5000 + i * 100}, priority=priority)
        elif mod == 1:
            t = engine.submit_task("io_simulation", {"delay": 0.002, "size": 2048}, priority=priority)
        else:
            t = engine.submit_task("transient_worker", {"tid": f"trans-{i}"}, priority=priority, max_retries=2, retry_delay=0.01)
        task_ids.append(t["id"])

    enqueue_time = time.time() - t_start
    print(f"[*] Enqueued {total_tasks} tasks in {enqueue_time * 1000:.2f}ms")

    # Await all completions
    deadline = time.time() + 15.0
    while time.time() < deadline:
        metrics = engine.get_metrics()
        completed = metrics.get("completed", 0) + metrics.get("failed", 0)
        if completed >= total_tasks:
            break
        time.sleep(0.05)

    total_duration = time.time() - t_start
    engine.stop()

    final_metrics = engine.get_metrics()
    completed = final_metrics.get("completed", 0)
    failed = final_metrics.get("failed", 0)
    retries = final_metrics.get("retry_count", 0)
    throughput = total_tasks / max(0.001, total_duration)

    latencies = collector.latencies
    latencies_sorted = sorted(latencies) if latencies else [0.0]
    p50 = latencies_sorted[int(len(latencies_sorted) * 0.5)] if latencies_sorted else 0.0
    p95 = latencies_sorted[min(int(len(latencies_sorted) * 0.95), len(latencies_sorted) - 1)] if latencies_sorted else 0.0

    report = {
        "benchmark_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_tasks": total_tasks,
        "max_workers": max_workers,
        "completed": completed,
        "failed": failed,
        "retried": retries,
        "total_duration_sec": round(total_duration, 4),
        "throughput_tasks_per_sec": round(throughput, 2),
        "latency_stats": {
            "avg_ms": round(final_metrics.get("latency_avg_seconds", 0) * 1000, 2),
            "min_ms": round(final_metrics.get("latency_min_seconds", 0) * 1000, 2),
            "p50_ms": round(p50 * 1000, 2),
            "p95_ms": round(p95 * 1000, 2),
            "max_ms": round(final_metrics.get("latency_max_seconds", 0) * 1000, 2),
        },
        "success_rate_percent": round((completed / total_tasks) * 100, 2),
    }

    with open("benchmark_report.json", "w") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 50)
    print("      DISTRIBUTED QUEUE BENCHMARK REPORT      ")
    print("=" * 50)
    print(f" Total Tasks     : {total_tasks}")
    print(f" Workers         : {max_workers} threads")
    print(f" Completed       : {completed} / {total_tasks} ({report['success_rate_percent']}%)")
    print(f" Retried/Glitch  : {retries} recovered")
    print(f" Total Duration  : {total_duration:.3f} s")
    print(f" Throughput      : {throughput:.1f} tasks/sec")
    print(f" Latency Avg     : {report['latency_stats']['avg_ms']} ms")
    print(f" Latency P50     : {report['latency_stats']['p50_ms']} ms")
    print(f" Latency P95     : {report['latency_stats']['p95_ms']} ms")
    print("=" * 50)
    print("[*] Benchmark report saved to benchmark_report.json\n")
    return report

if __name__ == "__main__":
    run_benchmark(total_tasks=50, max_workers=4)
