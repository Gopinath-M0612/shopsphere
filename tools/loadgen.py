#!/usr/bin/env python3
"""ShopSphere traffic generator.

Simulates shoppers: browse products, check stock, place orders, sometimes cancel.
Use it to create load for autoscaling tests, dashboards and incident drills.

    python tools/loadgen.py --url http://localhost:8080 --users 5 --duration 60

Only needs: pip install httpx
"""
import argparse
import random
import statistics
import threading
import time
from collections import Counter

import httpx

SKUS = ["EL-1001", "EL-1002", "EL-1003", "EL-1004", "HM-2001", "HM-2002",
        "HM-2003", "BK-3001", "BK-3002", "BK-3003", "FT-4001", "FT-4002"]


class Stats:
    def __init__(self):
        self.lock = threading.Lock()
        self.codes = Counter()
        self.latencies = []

    def record(self, name: str, status: int, seconds: float):
        with self.lock:
            self.codes[(name, status)] += 1
            self.latencies.append(seconds)


def shopper(base: str, stop_at: float, stats: Stats, user_id: int, think: float):
    email = f"user{user_id}@loadtest.local"
    if random.random() < 0.05:
        email = f"declined{user_id}@loadtest.local"  # exercises the payment-declined path
    with httpx.Client(base_url=base, timeout=10) as client:
        while time.time() < stop_at:
            action = random.choices(["browse", "search", "stock", "order", "orders"],
                                    weights=[40, 15, 15, 20, 10])[0]
            start = time.perf_counter()
            try:
                if action == "browse":
                    r = client.get("/api/catalog/products", params={"page": random.randint(1, 2), "page_size": 8})
                elif action == "search":
                    r = client.get("/api/catalog/products", params={"q": random.choice(["smart", "book", "mat", "lamp"])})
                elif action == "stock":
                    r = client.get(f"/api/inventory/stock/{random.choice(SKUS)}")
                elif action == "order":
                    items = [{"sku": s, "qty": random.randint(1, 2)} for s in random.sample(SKUS, random.randint(1, 3))]
                    r = client.post("/api/orders/orders", json={"customer_email": email, "items": items})
                    if r.status_code == 201 and random.random() < 0.1:
                        client.post(f"/api/orders/orders/{r.json()['id']}/cancel", json={"reason": "loadgen"})
                else:
                    r = client.get("/api/orders/orders", params={"email": email, "limit": 5})
                stats.record(action, r.status_code, time.perf_counter() - start)
            except httpx.HTTPError as exc:
                stats.record(action, 0, time.perf_counter() - start)
                print(f"[user {user_id}] {action} failed: {type(exc).__name__}")
            time.sleep(random.uniform(0, think))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--url", default="http://localhost:8080", help="gateway base URL")
    p.add_argument("--users", type=int, default=5, help="concurrent shoppers")
    p.add_argument("--duration", type=int, default=60, help="seconds to run")
    p.add_argument("--think", type=float, default=0.5, help="max pause between actions (seconds)")
    args = p.parse_args()

    stats = Stats()
    stop_at = time.time() + args.duration
    threads = [threading.Thread(target=shopper, args=(args.url, stop_at, stats, i, args.think), daemon=True)
               for i in range(args.users)]
    print(f"loadgen: {args.users} users for {args.duration}s against {args.url}")
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    total = sum(stats.codes.values())
    print(f"\nrequests: {total}")
    for (name, code), count in sorted(stats.codes.items()):
        print(f"  {name:<8} {code if code else 'ERR':>4}  {count}")
    if stats.latencies:
        lat = sorted(stats.latencies)
        p95 = lat[int(len(lat) * 0.95) - 1]
        print(f"latency  avg {statistics.mean(lat) * 1000:.0f} ms   p95 {p95 * 1000:.0f} ms   max {lat[-1] * 1000:.0f} ms")
    errors = sum(c for (_, code), c in stats.codes.items() if code == 0 or code >= 500)
    print(f"server errors: {errors} ({errors / total * 100:.1f}%)" if total else "no requests sent")


if __name__ == "__main__":
    main()
