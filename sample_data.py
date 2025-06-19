# sample_data.py
# ──────────────────────────────────────────────────────────
# Node / Pod Metrics
NODE_METRIC = {
    # ── 장애 케이스 ───────────────────────
    "node-a": {"cpu_usage": "92%", "memory_usage": "81%", "disk_usage": "89%"},

    # ── 정상(보통 부하) 케이스 ────────────
    "node-b": {"cpu_usage": "55%", "memory_usage": "48%", "disk_usage": "40%"},
    "node-c": {"cpu_usage": "23%", "memory_usage": "31%", "disk_usage": "28%"}
}

POD_METRIC = {
    # 부하 높은 파드 (node-a)
    "service-a-pod-123":{"memory_usage": "95%", "memory_limit": "512Mi", "cpu_usage": "87%", "memory_usage": "95%"},
    
    # 비교적 정상 (node-a)
    "checkout-service-pod-456": {"memory_usage": "60%", "memory_limit": "1Gi", "cpu_usage": "45%", "memory_usage": "60%"},

    # 기타 노드 (node-b, node-c)
    "auth-pod-abc": {"memory_usage": "42%", "memory_limit": "512Mi", "cpu_usage": "38%", "memory_usage": "42%"},
    "inventory-pod-999": {"memory_usage": "50%", "memory_limit": "1Gi", "cpu_usage": "30%", "memory_usage": "50%"},
}

# ─────────────────────────────────────────
# ② Event Logs  (OOMKilled, PVC, Probe 실패 등)
# ─────────────────────────────────────────
EVENT_LOG = {
    # 장애 – OOMKilled
    "service-a-pod-123": [
        {"reason": "Killing", "message": "OOMKilled", "@timestamp": "2025-06-19T02:40:00Z"}
    ],
    # 장애 – PVC 바인딩 실패
    "data-pvc": [
        {"reason": "ProvisioningFailed",
         "message": "no available persistent volumes found to bind",
         "@timestamp": "2025-06-19T03:00:00Z"}
    ],
    # 장애 – ReadinessProbe 실패
    "analytics-pod-777": [
        {"reason": "Unhealthy",
         "message": "Readiness probe failed: HTTP probe failed with statuscode: 500",
         "@timestamp": "2025-06-19T04:10:00Z"}
    ],
    # 정상 – 이벤트 없음
    "auth-pod-abc": [],
}

# ─────────────────────────────────────────
# ③ APM (평균 지연·에러율)
# ─────────────────────────────────────────
APM_SAMPLE = {
    # 장애 케이스
    "checkout-service": {"avg_latency_ms": 1250, "error_rate_pct": 4.8},
    "payment-api":      {"avg_latency_ms": 1350, "error_rate_pct": 6.7},

    # 정상 케이스
    "order-service":    {"avg_latency_ms": 420,  "error_rate_pct": 0.8},
    "inventory-service":{"avg_latency_ms": 310,  "error_rate_pct": 0.5},
    "auth-api":         {"avg_latency_ms": 270,  "error_rate_pct": 0.3},
}

# RAG docs (score, chunk)
RAG_SAMPLE = [
    (0.92, "2024-11-03 checkout-service latency 증가 → Redis 미스율 50% ↑ …"),
    (0.87, "2025-02-14 node-a CPU 90% 이상 과부하로 pod Pending …")
]

NODE_POD_MAP = {
    "node-a": ["service-a-pod-123", "checkout-service-pod-456"],
    "node-b": ["auth-pod-abc", "inventory-pod-999"],
    "node-c": ["analytics-pod-777", "report-pod-555"],
}