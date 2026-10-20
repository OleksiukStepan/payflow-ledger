#!/usr/bin/env python3
"""Replays PayFlow events the way the docs say PayFlow delivers them: duplicated, out of order, in parallel."""

import argparse
import hashlib
import hmac
import json
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

FIELDS = {"authorized": "authorized_amount", "captured": "captured_amount", "refunded": "refunded_amount"}


def build_delivery(events: list[dict[str, Any]], shuffle: bool, duplicates: int, rng: random.Random) -> list:
    delivery = events + [rng.choice(events) for _ in range(duplicates)] if events else []
    if shuffle:
        rng.shuffle(delivery)
    return delivery


def deliver(url: str, secret: bytes, event: dict[str, Any], retries: int) -> tuple[int, str]:
    # Same bytes and signature as PayFlowEventsSender.py; any non-2xx is retried with a growing pause.
    body = json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode()
    signature = hmac.new(secret, body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-PayFlow-Signature": signature}
    status, answer = 0, ""
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read()).get("status", "")
        except urllib.error.HTTPError as error:
            status, answer = error.code, error.read().decode(errors="replace")[:200]
        except (urllib.error.URLError, TimeoutError) as error:
            status, answer = 0, str(error)
        if attempt < retries:
            time.sleep(0.2 * 2**attempt)
    return status, answer


def check_expectations(expected: dict[str, Any], fetch: Callable[[str], Any]) -> list[tuple[str, str, str, str]]:
    """Returns (subject, field, expected, actual) rows; fetch(path) must return the parsed JSON of a GET."""
    rows = []
    for account_id, account in expected.items():
        balance = fetch(f"/accounts/{account_id}/balance") or {}
        items = (fetch(f"/accounts/{account_id}/transactions") or {}).get("items", [])
        for field in ("available", "pending"):
            rows.append((account_id, field, account[field], balance.get(field, "missing")))
        by_id = {item["authorization_id"]: item for item in items}
        for authorization_id, facts in account["authorizations"].items():
            item = by_id.get(authorization_id, {})
            rows.append((authorization_id, "status", facts["status"], item.get("status", "missing")))
            for field, api_field in FIELDS.items():
                rows.append((authorization_id, field, facts[field], str(item.get(api_field, "missing"))))
    return rows


def _http_fetch(base_url: str) -> Callable[[str], Any]:
    def fetch(path: str) -> Any:
        try:
            with urllib.request.urlopen(base_url + path, timeout=10) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError):
            return None

    return fetch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events_files", nargs="+", help="JSON files with arrays of events")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--secret", default="whsec_test_123")
    parser.add_argument("--shuffle", action="store_true", help="deliver in random order")
    parser.add_argument("--duplicates", type=int, default=0, help="extra copies of randomly picked events")
    parser.add_argument("--parallel", type=int, default=1, help="concurrent deliveries")
    parser.add_argument("--retries", type=int, default=3, help="extra attempts after a non-2xx answer")
    parser.add_argument("--seed", type=int, help="random seed, to reproduce a run")
    parser.add_argument("--expect", help="JSON file with expected balances and authorizations")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(10**6)
    events = []
    for path in args.events_files:
        with open(path, encoding="utf-8") as events_file:
            loaded = json.load(events_file)
        if not isinstance(loaded, list) or not all(isinstance(event, dict) for event in loaded):
            parser.error(f"{path} is not a JSON array of events")
        events.extend(loaded)
    delivery = build_delivery(events, args.shuffle, args.duplicates, random.Random(seed))

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        results = list(
            pool.map(
                lambda event: deliver(args.base_url + "/webhooks", args.secret.encode(), event, args.retries), delivery
            )
        )
    elapsed = time.perf_counter() - started

    outcomes = Counter(answer if 200 <= status < 300 else f"failed {status}" for status, answer in results)
    extra = len(delivery) - len(events)
    print(f"Delivered {len(delivery)} requests ({len(events)} from files + {extra} extra) in {elapsed:.2f}s")
    print(f"Seed {seed} (pass --seed {seed} to reproduce the same order)")
    print("Answers: " + ", ".join(f"{name} {count}" for name, count in sorted(outcomes.items())))
    failed = sum(count for name, count in outcomes.items() if name.startswith("failed"))

    mismatches = 0
    if args.expect:
        with open(args.expect, encoding="utf-8") as expect_file:
            rows = check_expectations(json.load(expect_file), _http_fetch(args.base_url))
        print(f"\n{'subject':<10} {'field':<11} {'expected':>10} {'actual':>10}")
        for subject, field, wanted, actual in rows:
            verdict = "" if wanted == actual else "  MISMATCH"
            mismatches += bool(verdict)
            print(f"{subject:<10} {field:<11} {wanted:>10} {actual:>10}{verdict}")
        print(f"\n{len(rows) - mismatches}/{len(rows)} checks match")

    return 1 if failed or mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
