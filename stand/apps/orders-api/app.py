import os
import random
import time
from typing import Any

import psycopg
from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

APP_PORT = int(os.getenv("APP_PORT", "8000"))
POSTGRES_DSN = os.getenv("POSTGRES_DSN", "postgresql://app:app@postgres:5432/app")

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
    "Total response bytes sent by orders-api",
    ["method", "path", "status"],
)

INFLIGHT_REQUESTS = Gauge(
    "http_inflight_requests",
    "Current in-flight inbound HTTP requests",
    ["path"],
)

DB_QUERIES = Counter(
    "db_queries_total",
    "Total database queries",
    ["operation", "status"],
)

DB_LATENCY = Histogram(
    "db_query_duration_seconds",
    "Database query latency in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.3, 1, 2),
)

DB_READY = Gauge(
    "db_ready",
    "Whether database is reachable",
)

ORDERS_CREATED_TOTAL = Counter(
    "orders_created_total",
    "Total created orders",
)

ORDERS_READ_TOTAL = Counter(
    "orders_read_total",
    "Total read orders",
)

ORDERS_SUMMARY_REQUESTS_TOTAL = Counter(
    "orders_summary_requests_total",
    "Total summary requests",
)

SLOW_REQUESTS_TOTAL = Counter(
    "slow_requests_total",
    "Total intentionally slow requests",
    ["path"],
)

INTENTIONAL_ERRORS_TOTAL = Counter(
    "intentional_errors_total",
    "Total intentional demo errors",
    ["path"],
)

ORDERS_IN_DB = Gauge(
    "orders_in_db",
    "Current number of orders in database",
)

ORDER_QUANTITY_SUM = Gauge(
    "orders_quantity_sum",
    "Sum of order quantities currently stored",
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


def db_connect() -> psycopg.Connection[Any]:
    return psycopg.connect(POSTGRES_DSN, autocommit=True)


def refresh_business_gauges(conn: psycopg.Connection[Any]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), COALESCE(SUM(quantity), 0) FROM orders;")
        count, quantity_sum = cur.fetchone()
        ORDERS_IN_DB.set(count)
        ORDER_QUANTITY_SUM.set(quantity_sum)


def init_db() -> None:
    create_sql = """
    CREATE TABLE IF NOT EXISTS orders (
        id BIGSERIAL PRIMARY KEY,
        item TEXT NOT NULL,
        quantity INTEGER NOT NULL CHECK (quantity > 0),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    for attempt in range(1, 31):
        try:
            with db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_sql)
                    cur.execute("SELECT COUNT(*) FROM orders;")
                    count = cur.fetchone()[0]
                    if count == 0:
                        cur.execute(
                            """
                            INSERT INTO orders (item, quantity)
                            VALUES
                                (%s, %s),
                                (%s, %s),
                                (%s, %s);
                            """,
                            ("book", 1, "notebook", 2, "pen", 5),
                        )
                refresh_business_gauges(conn)
            DB_READY.set(1)
            app.logger.info("Database initialized")
            return
        except Exception as exc:
            DB_READY.set(0)
            app.logger.warning("DB init attempt %s failed: %s", attempt, exc)
            time.sleep(2)

    raise RuntimeError("Could not initialize database after multiple retries")


def run_db(operation: str, fn):
    started_at = time.perf_counter()
    try:
        result = fn()
        DB_QUERIES.labels(operation=operation, status="ok").inc()
        DB_READY.set(1)
        return result
    except Exception:
        DB_QUERIES.labels(operation=operation, status="error").inc()
        DB_READY.set(0)
        raise
    finally:
        DB_LATENCY.labels(operation=operation).observe(time.perf_counter() - started_at)


@app.get("/")
def index():
    return jsonify(
        {
            "service": "orders-api",
            "status": "ok",
            "routes": [
                "/health",
                "/orders",
                "/orders/summary",
                "/orders/slow",
                "/error",
                "/metrics",
            ],
        }
    )


@app.get("/health")
def health():
    def _check():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return cur.fetchone()[0]

    value = run_db("healthcheck", _check)
    return jsonify({"service": "orders-api", "db": "ok", "value": value})


@app.get("/orders")
def list_orders():
    limit = request.args.get("limit", default=20, type=int)
    limit = max(1, min(limit, 100))

    def _list():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, item, quantity, created_at
                    FROM orders
                    ORDER BY id DESC
                    LIMIT %s;
                    """,
                    (limit,),
                )
                rows = cur.fetchall()
                refresh_business_gauges(conn)
                result = []
                for row in rows:
                    result.append(
                        {
                            "id": row[0],
                            "item": row[1],
                            "quantity": row[2],
                            "created_at": row[3].isoformat(),
                        }
                    )
                return result

    rows = run_db("select_orders", _list)
    ORDERS_READ_TOTAL.inc(len(rows))
    return jsonify({"count": len(rows), "orders": rows})


@app.post("/orders")
def create_order():
    payload = request.get_json(silent=True) or {}
    item = str(payload.get("item", "generated-item")).strip() or "generated-item"
    quantity = int(payload.get("quantity", 1))
    quantity = max(1, min(quantity, 100))

    if payload.get("simulate_slow"):
        delay = random.uniform(0.15, 0.7)
        time.sleep(delay)
        SLOW_REQUESTS_TOTAL.labels(path="/orders").inc()

    def _create():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO orders (item, quantity)
                    VALUES (%s, %s)
                    RETURNING id, item, quantity, created_at;
                    """,
                    (item, quantity),
                )
                row = cur.fetchone()
                refresh_business_gauges(conn)
                return {
                    "id": row[0],
                    "item": row[1],
                    "quantity": row[2],
                    "created_at": row[3].isoformat(),
                }

    order = run_db("insert_order", _create)
    ORDERS_CREATED_TOTAL.inc()
    return jsonify(order), 201


@app.get("/orders/summary")
def orders_summary():
    ORDERS_SUMMARY_REQUESTS_TOTAL.inc()

    def _summary():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*), COALESCE(SUM(quantity), 0), COALESCE(AVG(quantity), 0)
                    FROM orders;
                    """
                )
                count, quantity_sum, avg_quantity = cur.fetchone()
                refresh_business_gauges(conn)
                return {
                    "orders_count": int(count),
                    "quantity_sum": int(quantity_sum),
                    "avg_quantity": float(avg_quantity),
                }

    data = run_db("summary_orders", _summary)
    return jsonify(data)


@app.get("/orders/slow")
def slow_orders():
    delay_ms = request.args.get("delay_ms", default=300, type=int)
    delay_ms = max(50, min(delay_ms, 3000))
    SLOW_REQUESTS_TOTAL.labels(path="/orders/slow").inc()
    time.sleep(delay_ms / 1000.0)

    def _slow_query():
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, item, quantity, created_at
                    FROM orders
                    ORDER BY created_at DESC
                    LIMIT 5;
                    """
                )
                rows = cur.fetchall()
                refresh_business_gauges(conn)
                return [
                    {
                        "id": row[0],
                        "item": row[1],
                        "quantity": row[2],
                        "created_at": row[3].isoformat(),
                    }
                    for row in rows
                ]

    rows = run_db("slow_select_orders", _slow_query)
    return jsonify({"delay_ms": delay_ms, "orders": rows})


@app.get("/error")
def make_error():
    INTENTIONAL_ERRORS_TOTAL.labels(path="/error").inc()
    return jsonify({"service": "orders-api", "error": "intentional demo error"}), 500


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=APP_PORT, threaded=True, use_reloader=False)