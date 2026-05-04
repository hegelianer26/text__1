import os
import random
import time

import requests

GATEWAY_API_URL = os.getenv("GATEWAY_API_URL", "http://gateway-api:8001")
LOOP_INTERVAL_SECONDS = float(os.getenv("LOOP_INTERVAL_SECONDS", "0.6"))
BURST_EVERY_N = int(os.getenv("BURST_EVERY_N", "20"))
BURST_SIZE = int(os.getenv("BURST_SIZE", "18"))

ITEMS = [
    "book",
    "notebook",
    "pen",
    "lamp",
    "cable",
    "sticker",
    "paper",
    "charger",
]

counter = 0


def do_request() -> None:
    action = random.choices(
        population=["create", "list", "summary", "slow", "error"],
        weights=[0.42, 0.24, 0.14, 0.12, 0.08],
        k=1,
    )[0]

    if action == "create":
        payload = {
            "item": random.choice(ITEMS),
            "quantity": random.randint(1, 5),
            "simulate_slow": random.random() < 0.18,
        }
        resp = requests.post(f"{GATEWAY_API_URL}/proxy/orders", json=payload, timeout=10)
        print(f"[traffic-gen] create -> {resp.status_code}")

    elif action == "list":
        limit = random.randint(5, 30)
        resp = requests.get(f"{GATEWAY_API_URL}/proxy/orders", params={"limit": limit}, timeout=10)
        print(f"[traffic-gen] list(limit={limit}) -> {resp.status_code}")

    elif action == "summary":
        resp = requests.get(f"{GATEWAY_API_URL}/proxy/orders/summary", timeout=10)
        print(f"[traffic-gen] summary -> {resp.status_code}")

    elif action == "slow":
        delay_ms = random.choice([200, 400, 800, 1200])
        resp = requests.get(f"{GATEWAY_API_URL}/proxy/orders/slow", params={"delay_ms": delay_ms}, timeout=15)
        print(f"[traffic-gen] slow(delay_ms={delay_ms}) -> {resp.status_code}")

    else:
        resp = requests.get(f"{GATEWAY_API_URL}/proxy/error", timeout=10)
        print(f"[traffic-gen] error -> {resp.status_code}")


def do_burst() -> None:
    print(f"[traffic-gen] burst started size={BURST_SIZE}")
    for _ in range(BURST_SIZE):
        try:
            payload = {
                "item": random.choice(ITEMS),
                "quantity": random.randint(1, 3),
                "simulate_slow": random.random() < 0.25,
            }
            resp = requests.post(f"{GATEWAY_API_URL}/proxy/orders", json=payload, timeout=15)
            print(f"[traffic-gen] burst create -> {resp.status_code}")
        except Exception as exc:
            print(f"[traffic-gen] burst failed: {exc}")


def main() -> None:
    global counter
    print(
        f"[traffic-gen] started target={GATEWAY_API_URL} "
        f"interval={LOOP_INTERVAL_SECONDS}s burst_every={BURST_EVERY_N} burst_size={BURST_SIZE}"
    )

    while True:
        counter += 1
        try:
            if counter % BURST_EVERY_N == 0:
                do_burst()
            else:
                do_request()
        except Exception as exc:
            print(f"[traffic-gen] request failed: {exc}")

        time.sleep(LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()