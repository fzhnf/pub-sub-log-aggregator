#!/usr/bin/env python
"""
Benchmark: throughput vs batch size
Produces: throughput.csv + throughput.png
Run:  python bench_throughput.py
"""

# pyright: reportUnknownMemberType=false

import asyncio
import csv
import time
import statistics
import matplotlib.pyplot as plt
from httpx import ASGITransport, AsyncClient
from main import app, lifespan

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------
BATCH_SIZES = [1, 10, 50, 100, 200, 500, 1000]  # spec limit
TOTAL_EVENTS = 5_000  # keep constant
WARMUP_EVENTS = 200
URL = "http://localhost:8080/publish"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
async def post_batch(client: AsyncClient, batch_size: int) -> float:
    """Return wall-clock time for one HTTP POST containing <batch_size> events."""
    events = [
        {
            "topic": "bench.throughput",
            "event_id": f"bench-{int(time.time() * 1e6)}-{i}",
            "timestamp": "2025-10-23T12:00:00Z",
            "source": "bench",
            "payload": {"seq": i, "data": "x" * 100},  # 100 B payload
        }
        for i in range(batch_size)
    ]
    t0 = time.perf_counter()
    r = await client.post(URL, json={"events": events})
    t1 = time.perf_counter()
    if r.status_code != 202:
        raise RuntimeError(r.text)
    return t1 - t0


async def bench_one(client: AsyncClient, batch_size: int) -> tuple[float, float]:
    """Return (events_per_sec, mean_http_latency)."""
    batches = TOTAL_EVENTS // batch_size
    latencies: list[float] = []

    # warm-up
    for _ in range(WARMUP_EVENTS // batch_size):
        _ = await post_batch(client, batch_size)

    # real run
    t0 = time.perf_counter()
    for _ in range(batches):
        latencies.append(await post_batch(client, batch_size))
    total_time = time.perf_counter() - t0

    events_per_sec = TOTAL_EVENTS / total_time
    mean_latency = statistics.mean(latencies)
    return events_per_sec, mean_latency


async def main():
    csv_rows: list[tuple[int, float, float]] = []

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=30.0
    ) as client:
        async with lifespan(app):
            await asyncio.sleep(0.5)  # let consumer start

            for bs in BATCH_SIZES:
                print(f"Running batch size {bs} ...")
                eps, lat = await bench_one(client, bs)
                csv_rows.append((bs, eps, lat))
                print(f"  → {eps:,.0f} events/s   (latency {lat * 1000:.1f} ms)")

    # ------------------------------------------------------------------
    # CSV output
    # ------------------------------------------------------------------
    with open("throughput.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["batch_size", "events_per_sec", "http_latency_ms"])
        for bs, eps, lat in csv_rows:
            writer.writerow([bs, round(eps, 2), round(lat * 1000, 2)])

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------
    xs, ys, _ = zip(*csv_rows)
    _ = plt.figure(figsize=(6, 4))
    _ = plt.plot(xs, ys, marker="o")
    plt.xscale("log")
    _ = plt.xlabel("Batch size (events per HTTP POST)")
    _ = plt.ylabel("Throughput (events / second)")
    _ = plt.title("Pub-Sub Aggregator – Throughput vs Batch Size")
    plt.grid(True, which="both", ls="--")
    plt.tight_layout()
    plt.savefig("throughput.png", dpi=300)
    print("Saved throughput.csv and throughput.png")


if __name__ == "__main__":
    asyncio.run(main())
