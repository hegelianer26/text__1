# План требований к наблюдаемости

Сгенерировано автоматически по docker-compose.yml и observability.yaml.

## gateway-api

- Модули: `http_server, http_client, container_metrics`

### Метрики и требования

- **Доступность таргета (up)** (ОБЯЗАТЕЛЬНО)
  - `max(up{job="gateway-api"})`
- **Интенсивность HTTP-запросов** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(http_requests_total{job="gateway-api"}[5m]))`
- **HTTP-ошибки 5xx** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(http_requests_total{job="gateway-api",status=~"5.."}[5m]))`
- **Задержка HTTP p95** (РЕКОМЕНДУЕТСЯ)
  - `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="gateway-api"}[5m])) by (le))`
- **Текущие inflight-запросы** (РЕКОМЕНДУЕТСЯ)
  - `sum(http_inflight_requests{job="gateway-api"})`
- **Доступность downstream** (РЕКОМЕНДУЕТСЯ)
  - `min(downstream_up{job="gateway-api"})`
- **Исходящие HTTP-запросы** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(outbound_http_requests_total{job="gateway-api"}[5m]))`
- **Ошибки downstream-вызовов** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(outbound_http_requests_total{job="gateway-api",status=~"5..|error"}[5m]))`
- **Задержка downstream-вызовов p95** (РЕКОМЕНДУЕТСЯ)
  - `histogram_quantile(0.95, sum(rate(outbound_http_request_duration_seconds_bucket{job="gateway-api"}[5m])) by (le))`
- **Потребление CPU контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_cpu_usage_seconds_total{job="cadvisor",service="gateway-api"}[5m]))`
- **Потребление памяти контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(container_memory_usage_bytes{job="cadvisor",service="gateway-api"})`
- **Входящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_receive_bytes_total{job="cadvisor",service="gateway-api"}[5m]))`
- **Исходящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_transmit_bytes_total{job="cadvisor",service="gateway-api"}[5m]))`

### Базовые алерты

- **gateway_api_TargetDown**
  - `expr: max(up{job="gateway-api"}) == 0`
  - `for: 2m`
- **gateway_api_HighHttpErrorRate**
  - `expr: (sum(rate(http_requests_total{job="gateway-api",status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total{job="gateway-api"}[5m])), 0.001)) > 0.05`
  - `for: 5m`
- **gateway_api_HighHttpLatencyP95**
  - `expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="gateway-api"}[5m])) by (le)) > 0.75`
  - `for: 5m`
- **gateway_api_DownstreamUnavailable**
  - `expr: min(downstream_up{job="gateway-api"}) == 0`
  - `for: 2m`

## grafana

- Модули: `container_metrics`

### Метрики и требования

- **Потребление CPU контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_cpu_usage_seconds_total{job="cadvisor",service="grafana"}[5m]))`
- **Потребление памяти контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(container_memory_usage_bytes{job="cadvisor",service="grafana"})`
- **Входящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_receive_bytes_total{job="cadvisor",service="grafana"}[5m]))`
- **Исходящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_transmit_bytes_total{job="cadvisor",service="grafana"}[5m]))`

## orders-api

- Модули: `http_server, postgres_client, business_orders, container_metrics`

### Метрики и требования

- **Доступность таргета (up)** (ОБЯЗАТЕЛЬНО)
  - `max(up{job="orders-api"})`
- **Интенсивность HTTP-запросов** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(http_requests_total{job="orders-api"}[5m]))`
- **HTTP-ошибки 5xx** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(http_requests_total{job="orders-api",status=~"5.."}[5m]))`
- **Задержка HTTP p95** (РЕКОМЕНДУЕТСЯ)
  - `histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="orders-api"}[5m])) by (le))`
- **Текущие inflight-запросы** (РЕКОМЕНДУЕТСЯ)
  - `sum(http_inflight_requests{job="orders-api"})`
- **Доступность БД на уровне приложения** (ОБЯЗАТЕЛЬНО)
  - `max(db_ready{job="orders-api"})`
- **Успешные запросы к БД** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(db_queries_total{job="orders-api",status="ok"}[5m]))`
- **Ошибки запросов к БД** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(db_queries_total{job="orders-api",status="error"}[5m]))`
- **Задержка запросов к БД p95** (РЕКОМЕНДУЕТСЯ)
  - `histogram_quantile(0.95, sum(rate(db_query_duration_seconds_bucket{job="orders-api"}[5m])) by (le, operation))`
- **Количество заказов в БД** (РЕКОМЕНДУЕТСЯ)
  - `max(orders_in_db{job="orders-api"})`
- **Создание заказов** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(orders_created_total{job="orders-api"}[5m]))`
- **Чтение заказов** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(orders_read_total{job="orders-api"}[5m]))`
- **Медленные запросы** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(slow_requests_total{job="orders-api"}[5m]))`
- **Потребление CPU контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_cpu_usage_seconds_total{job="cadvisor",service="orders-api"}[5m]))`
- **Потребление памяти контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(container_memory_usage_bytes{job="cadvisor",service="orders-api"})`
- **Входящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_receive_bytes_total{job="cadvisor",service="orders-api"}[5m]))`
- **Исходящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_transmit_bytes_total{job="cadvisor",service="orders-api"}[5m]))`

### Базовые алерты

- **orders_api_TargetDown**
  - `expr: max(up{job="orders-api"}) == 0`
  - `for: 2m`
- **orders_api_HighHttpErrorRate**
  - `expr: (sum(rate(http_requests_total{job="orders-api",status=~"5.."}[5m])) / clamp_min(sum(rate(http_requests_total{job="orders-api"}[5m])), 0.001)) > 0.05`
  - `for: 5m`
- **orders_api_HighHttpLatencyP95**
  - `expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket{job="orders-api"}[5m])) by (le)) > 0.75`
  - `for: 5m`
- **orders_api_DbNotReady**
  - `expr: max(db_ready{job="orders-api"}) == 0`
  - `for: 2m`

## postgres

- Модули: `postgres_exporter, container_metrics`

### Метрики и требования

- **Доступность postgres_exporter (up)** (ОБЯЗАТЕЛЬНО)
  - `max(up{job="postgres"})`
- **Активные соединения** (ОБЯЗАТЕЛЬНО)
  - `pg_stat_activity_count{job="postgres"}`
- **Скорость транзакций** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(pg_stat_database_xact_commit{job="postgres"}[5m])) + sum(rate(pg_stat_database_xact_rollback{job="postgres"}[5m]))`
- **Скорость дедлоков** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(pg_stat_database_deadlocks{job="postgres"}[5m]))`
- **Потребление CPU контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_cpu_usage_seconds_total{job="cadvisor",service="postgres"}[5m]))`
- **Потребление памяти контейнером** (РЕКОМЕНДУЕТСЯ)
  - `sum(container_memory_usage_bytes{job="cadvisor",service="postgres"})`
- **Входящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_receive_bytes_total{job="cadvisor",service="postgres"}[5m]))`
- **Исходящий сетевой трафик контейнера** (РЕКОМЕНДУЕТСЯ)
  - `sum(rate(container_network_transmit_bytes_total{job="cadvisor",service="postgres"}[5m]))`

### Базовые алерты

- **postgres_TargetDown**
  - `expr: max(up{job="postgres"}) == 0`
  - `for: 2m`

## host

- Модули: `host_metrics`

### Метрики и требования

- **Доступность node_exporter** (ОБЯЗАТЕЛЬНО)
  - `max(up{job="node"})`
- **Загрузка CPU хоста** (РЕКОМЕНДУЕТСЯ)
  - `100 * (1 - avg(rate(node_cpu_seconds_total{job="node",mode="idle"}[5m])))`
- **Load average хоста** (РЕКОМЕНДУЕТСЯ)
  - `node_load1{job="node"}`
- **Доступная память хоста** (РЕКОМЕНДУЕТСЯ)
  - `node_memory_MemAvailable_bytes{job="node"}`
- **Свободное дисковое пространство хоста** (РЕКОМЕНДУЕТСЯ)
  - `sum(node_filesystem_avail_bytes{job="node",fstype!=""})`

### Базовые алерты

- **HostTargetDown**
  - `expr: max(up{job="node"}) == 0`
  - `for: 2m`
- **HostHighCpu**
  - `expr: 100 * (1 - avg(rate(node_cpu_seconds_total{job="node",mode="idle"}[5m]))) > 90.0`
  - `for: 5m`
