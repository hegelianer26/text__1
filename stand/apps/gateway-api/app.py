import os
import time

import requests
from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

APP_PORT = int(os.getenv("APP_PORT", "8001"))
ORDERS_API_URL = os.getenv("ORDERS_API_URL", "http://orders-api:8000")

app = Flask(__name__)

HTTP_REQUESTS = Counter(
    "http_requests_total",
    "Total inbound HTTP requests",
    ["method", "path", "status"],
)

HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Inbound HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.3, 0.5, 1, 2, 5),
)

INBOUND_RESPONSE_BYTES = Counter(
    "http_response_bytes_total",
    "Total response bytes sent by gateway-api",
    ["method", "path", "status"],
)

INFLIGHT_REQUESTS = Gauge(
    "http_inflight_requests",
    "Current in-flight inbound HTTP requests",
    ["path"],
)

OUTBOUND_REQUESTS = Counter(
    "outbound_http_requests_total",
    "Total outbound HTTP requests from gateway-api",
    ["method", "target", "status"],
)

OUTBOUND_LATENCY = Histogram(
    "outbound_http_request_duration_seconds",
    "Outbound HTTP request latency in seconds",
    ["method", "target"],
    buckets=(0.005, 0.01, 0.05, 0.1, 0.3, 0.5, 1, 2, 5),
)

OUTBOUND_RESPONSE_BYTES = Counter(
    "outbound_http_response_bytes_total",
    "Total response bytes received by gateway-api from downstream",
    ["method", "target", "status"],
)

DOWNSTREAM_UP = Gauge(
    "downstream_up",
    "Whether downstream orders-api is reachable",
    ["target"],
)

PROXY_ACTIONS_TOTAL = Counter(
    "proxy_actions_total",
    "Gateway actions by type",
    ["action", "status"],
)


def path_label() -> str:
    if request.url_rule is not None:
        return request.url_rule.rule
    return request.path


@app.before_request
def before_request() -> None:
    g.request_started_at = time.perf_counter()
    g.path_label = path_label()
    INFLIGHT_REQUESTS.labels(path=g.path_label).inc()


@app.after_request
def after_request(response):
    started_at = getattr(g, "request_started_at", None)
    current_path = getattr(g, "path_label", path_label())

    INFLIGHT_REQUESTS.labels(path=current_path).dec()

    if started_at is not None:
        duration = time.perf_counter() - started_at
        status_code = str(response.status_code)

        HTTP_REQUESTS.labels(
            method=request.method,
            path=current_path,
            status=status_code,
        ).inc()

        HTTP_LATENCY.labels(
            method=request.method,
            path=current_path,
        ).observe(duration)

        body_size = len(response.get_data() or b"")
        INBOUND_RESPONSE_BYTES.labels(
            method=request.method,
            path=current_path,
            status=status_code,
        ).inc(body_size)

    return response


def proxy_to_orders(method: str, path: str, *, params=None, json_body=None, action: str = "unknown"):
    url = f"{ORDERS_API_URL}{path}"
    started_at = time.perf_counter()

    try:
        resp = requests.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            timeout=5,
        )
        status_code = str(resp.status_code)
        DOWNSTREAM_UP.labels(target="orders-api").set(1)

        OUTBOUND_REQUESTS.labels(
            method=method,
            target=path,
            status=status_code,
        ).inc()

        OUTBOUND_RESPONSE_BYTES.labels(
            method=method,
            target=path,
            status=status_code,
        ).inc(len(resp.content or b""))

        if resp.status_code >= 500:
            PROXY_ACTIONS_TOTAL.labels(action=action, status="downstream_5xx").inc()
        else:
            PROXY_ACTIONS_TOTAL.labels(action=action, status="ok").inc()

        return Response(
            response=resp.content,
            status=resp.status_code,
            content_type=resp.headers.get("Content-Type", "application/json"),
        )

    except requests.RequestException as exc:
        DOWNSTREAM_UP.labels(target="orders-api").set(0)
        OUTBOUND_REQUESTS.labels(method=method, target=path, status="error").inc()
        PROXY_ACTIONS_TOTAL.labels(action=action, status="network_error").inc()
        return (
            jsonify(
                {
                    "service": "gateway-api",
                    "error": "orders-api unavailable",
                    "details": str(exc),
                }
            ),
            502,
        )
    finally:
        OUTBOUND_LATENCY.labels(method=method, target=path).observe(time.perf_counter() - started_at)


@app.get("/")
def index():
    return jsonify(
        {
            "service": "gateway-api",
            "status": "ok",
            "routes": [
                "/health",
                "/proxy/orders",
                "/proxy/orders/summary",
                "/proxy/orders/slow",
                "/proxy/error",
                "/metrics",
            ],
            "orders_api_url": ORDERS_API_URL,
        }
    )


@app.get("/health")
def health():
    return jsonify({"service": "gateway-api", "status": "ok"})


@app.get("/proxy/orders")
def proxy_list_orders():
    limit = request.args.get("limit", default=20, type=int)
    return proxy_to_orders("GET", "/orders", params={"limit": limit}, action="list_orders")


@app.post("/proxy/orders")
def proxy_create_order():
    payload = request.get_json(silent=True) or {}
    return proxy_to_orders("POST", "/orders", json_body=payload, action="create_order")


@app.get("/proxy/orders/summary")
def proxy_orders_summary():
    return proxy_to_orders("GET", "/orders/summary", action="orders_summary")


@app.get("/proxy/orders/slow")
def proxy_orders_slow():
    delay_ms = request.args.get("delay_ms", default=300, type=int)
    return proxy_to_orders("GET", "/orders/slow", params={"delay_ms": delay_ms}, action="slow_call")


@app.get("/proxy/error")
def proxy_error():
    return proxy_to_orders("GET", "/error", action="forced_error")


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=APP_PORT, threaded=True, use_reloader=False)