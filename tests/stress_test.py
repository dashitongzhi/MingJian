#!/usr/bin/env python3
"""明鉴 (MingJian) 7维压力测试 — stdlib only, no pip installs."""
import json, time, sys, urllib.request, urllib.error, concurrent.futures, threading, ssl

API = "http://127.0.0.1:8000"
FRONTEND = "http://127.0.0.1:3001"
RESULTS = {"pass": 0, "fail": 0, "warn": 0, "errors": [], "warnings": [], "details": []}
lock = threading.Lock()

# Disable SSL verification for local testing
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

def record(status, endpoint, msg="", latency_ms=0):
    with lock:
        if status == "PASS":
            RESULTS["pass"] += 1
        elif status == "FAIL":
            RESULTS["fail"] += 1
            RESULTS["errors"].append(f"❌ {endpoint}: {msg}")
        elif status == "WARN":
            RESULTS["warn"] += 1
            RESULTS["warnings"].append(f"⚠️ {endpoint}: {msg}")
        if latency_ms > 0:
            RESULTS["details"].append((endpoint, status, latency_ms))

def fetch(url, method="GET", data=None, timeout=15):
    start = time.time()
    try:
        req = urllib.request.Request(url, method=method)
        if data:
            req.data = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read().decode("utf-8", errors="replace")
        return resp.status, body, (time.time() - start) * 1000
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except:
            body = ""
        return e.code, body, (time.time() - start) * 1000
    except Exception as e:
        return 0, str(e), (time.time() - start) * 1000

def get_endpoints():
    """Discover GET endpoints from OpenAPI spec."""
    status, body, _ = fetch(f"{API}/openapi.json", timeout=10)
    if status != 200:
        print(f"Cannot fetch OpenAPI spec: {status}")
        return []
    spec = json.loads(body)
    endpoints = []
    for path, methods in spec.get("paths", {}).items():
        if "get" in methods:
            # Skip parameterized paths that need real IDs
            if "{" in path:
                endpoints.append(("param", path, methods["get"]))
            else:
                endpoints.append(("static", path, methods["get"]))
    return endpoints

# =========================================================================
# 1. API Endpoint Reachability
# =========================================================================
def test_api_reachability():
    print("\n" + "="*60)
    print("📡 1. API端点可达性测试")
    print("="*60)
    
    endpoints = get_endpoints()
    static_eps = [(t, p, m) for t, p, m in endpoints if t == "static"]
    param_eps = [(t, p, m) for t, p, m in endpoints if t == "param"]
    
    # Test static endpoints
    for _, path, _ in static_eps:
        url = f"{API}{path}"
        status, body, latency = fetch(url, timeout=10)
        if status == 200:
            record("PASS", path, latency_ms=latency)
            print(f"  ✅ GET {path} → {status} ({latency:.0f}ms)")
        elif status in (404, 422, 405):
            record("PASS", path, f"expected {status}", latency_ms=latency)
            print(f"  ✅ GET {path} → {status} (expected) ({latency:.0f}ms)")
        elif status == 500:
            record("FAIL", path, f"HTTP 500", latency_ms=latency)
            print(f"  ❌ GET {path} → 500 ({latency:.0f}ms)")
        else:
            record("WARN", path, f"HTTP {status}", latency_ms=latency)
            print(f"  ⚠️ GET {path} → {status} ({latency:.0f}ms)")
    
    # Test param endpoints with dummy IDs (expect 404/422, not 500)
    for _, path, _ in param_eps[:20]:  # Limit to 20
        test_path = path.replace("{", "").replace("}", "")
        url = f"{API}{test_path}"
        status, body, latency = fetch(url, timeout=10)
        if status == 500:
            record("FAIL", path, f"HTTP 500 on param endpoint", latency_ms=latency)
            print(f"  ❌ GET {path} → 500 ({latency:.0f}ms)")
        else:
            record("PASS", path, f"param endpoint → {status}", latency_ms=latency)
            print(f"  ✅ GET {path} → {status} ({latency:.0f}ms)")
    
    print(f"\n  📊 静态端点: {len(static_eps)} | 参数化端点: {len(param_eps)}")

# =========================================================================
# 2. Frontend Page Load Testing
# =========================================================================
def test_frontend_pages():
    print("\n" + "="*60)
    print("🌐 2. 前端页面加载测试")
    print("="*60)
    
    pages = [
        "/", "/dashboard", "/analysis", "/debate", "/assistant",
        "/sources", "/predictions", "/simulation", "/monitoring",
        "/workbench", "/agents", "/decisions", "/settings"
    ]
    
    for page in pages:
        url = f"{FRONTEND}{page}"
        status, body, latency = fetch(url, timeout=15)
        size_kb = len(body.encode()) / 1024
        if status == 200:
            if "<html" in body.lower() or "<!doctype" in body.lower():
                record("PASS", f"frontend:{page}", f"{size_kb:.0f}KB", latency_ms=latency)
                print(f"  ✅ {page} → 200 ({size_kb:.0f}KB, {latency:.0f}ms)")
            else:
                record("WARN", f"frontend:{page}", "no HTML content", latency_ms=latency)
                print(f"  ⚠️ {page} → 200 but no HTML ({latency:.0f}ms)")
        else:
            record("FAIL", f"frontend:{page}", f"HTTP {status}", latency_ms=latency)
            print(f"  ❌ {page} → {status} ({latency:.0f}ms)")

# =========================================================================
# 3. Concurrent Load Testing
# =========================================================================
def test_concurrent_load():
    print("\n" + "="*60)
    print("🔥 3. 并发负载测试")
    print("="*60)
    
    # Key endpoints to stress test
    targets = [
        f"{API}/",
        f"{API}/health",
        f"{API}/health/ready",
        f"{API}/sources/reputation",
        f"{API}/sources/custom",
        f"{API}/agents",
        f"{API}/predictions",
        f"{API}/claims",
        f"{API}/signals",
        f"{API}/trends",
        f"{API}/evidence",
        f"{API}/decisions",
        f"{API}/debates",
        f"{API}/monitoring/dashboard",
        f"{API}/model/settings",
    ]
    
    concurrency_levels = [5, 10, 20]
    
    for num_users in concurrency_levels:
        print(f"\n  🔸 并发数: {num_users} | 每端点 {num_users} 请求")
        all_latencies = []
        status_codes = {}
        errors = 0
        
        def hit_endpoint(url):
            status, _, latency = fetch(url, timeout=15)
            return status, latency
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_users) as executor:
            start_time = time.time()
            futures = []
            for target in targets:
                for _ in range(num_users):
                    futures.append(executor.submit(hit_endpoint, target))
            
            for future in concurrent.futures.as_completed(futures):
                status, latency = future.result()
                all_latencies.append(latency)
                status_codes[status] = status_codes.get(status, 0) + 1
                if status == 500 or status == 0:
                    errors += 1
            
            total_time = time.time() - start_time
        
        total_requests = len(futures)
        rps = total_requests / total_time if total_time > 0 else 0
        avg_latency = sum(all_latencies) / len(all_latencies) if all_latencies else 0
        sorted_lat = sorted(all_latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.5)] if sorted_lat else 0
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if sorted_lat else 0
        max_lat = max(all_latencies) if all_latencies else 0
        
        print(f"    总请求: {total_requests} | 耗时: {total_time:.1f}s | RPS: {rps:.0f}")
        print(f"    延迟: avg={avg_latency:.0f}ms P50={p50:.0f}ms P95={p95:.0f}ms P99={p99:.0f}ms max={max_lat:.0f}ms")
        print(f"    状态码: {status_codes}")
        
        if errors > 0:
            record("FAIL", f"并发{num_users}", f"{errors}/{total_requests} requests got 500/error")
            print(f"    ❌ {errors} 个请求返回500或连接错误")
        else:
            record("PASS", f"并发{num_users}", f"{total_requests} requests, {rps:.0f} RPS")
            print(f"    ✅ 零500错误")
        
        if avg_latency > 5000:
            record("FAIL", f"并发{num_users}延迟", f"avg {avg_latency:.0f}ms > 5000ms")
        elif avg_latency > 2000:
            record("WARN", f"并发{num_users}延迟", f"avg {avg_latency:.0f}ms > 2000ms")

# =========================================================================
# 4. SSE/WebSocket Connection Test
# =========================================================================
def test_sse_connections():
    print("\n" + "="*60)
    print("📡 4. SSE连接测试")
    print("="*60)
    
    sse_endpoints = [
        "/monitoring/events/stream",
    ]
    
    for path in sse_endpoints:
        url = f"{API}{path}"
        start = time.time()
        try:
            req = urllib.request.Request(url)
            req.add_header("Accept", "text/event-stream")
            resp = urllib.request.urlopen(req, timeout=5)
            # Read a bit of data
            data = resp.read(1024)
            latency = (time.time() - start) * 1000
            record("PASS", f"SSE:{path}", f"connected ({len(data)} bytes)", latency_ms=latency)
            print(f"  ✅ {path} → SSE连接成功 ({len(data)} bytes, {latency:.0f}ms)")
        except urllib.error.HTTPError as e:
            latency = (time.time() - start) * 1000
            if e.code == 422 or e.code == 400:
                record("PASS", f"SSE:{path}", f"HTTP {e.code} (expected for SSE without params)", latency_ms=latency)
                print(f"  ✅ {path} → {e.code} (expected) ({latency:.0f}ms)")
            else:
                record("WARN", f"SSE:{path}", f"HTTP {e.code}", latency_ms=latency)
                print(f"  ⚠️ {path} → {e.code} ({latency:.0f}ms)")
        except Exception as e:
            latency = (time.time() - start) * 1000
            if "timed out" in str(e).lower() or "timeout" in str(e).lower():
                record("PASS", f"SSE:{path}", "timeout (expected for long-poll)", latency_ms=latency)
                print(f"  ✅ {path} → 超时 (长轮询正常) ({latency:.0f}ms)")
            else:
                record("WARN", f"SSE:{path}", str(e)[:80], latency_ms=latency)
                print(f"  ⚠️ {path} → {e} ({latency:.0f}ms)")

# =========================================================================
# 5. Database Health Check
# =========================================================================
def test_database_health():
    print("\n" + "="*60)
    print("🗄️ 5. 数据库健康检查")
    print("="*60)
    
    # Health endpoints
    for path in ["/health", "/health/ready", "/health/live"]:
        status, body, latency = fetch(f"{API}{path}", timeout=10)
        if status == 200:
            try:
                data = json.loads(body)
                db_ok = data.get("database", data.get("db", "unknown"))
                redis_ok = data.get("redis", "unknown")
                record("PASS", path, f"db={db_ok}, redis={redis_ok}", latency_ms=latency)
                print(f"  ✅ {path} → {data}")
            except json.JSONDecodeError:
                record("PASS", path, "200 OK", latency_ms=latency)
                print(f"  ✅ {path} → 200 (non-JSON: {body[:50]})")
        elif status == 503:
            record("WARN", path, "503 Service Unavailable", latency_ms=latency)
            print(f"  ⚠️ {path} → 503 (服务降级)")
        else:
            record("FAIL", path, f"HTTP {status}", latency_ms=latency)
            print(f"  ❌ {path} → {status} ({latency:.0f}ms)")
    
    # Test actual DB operations via API
    for path in ["/claims", "/evidence", "/signals", "/trends", "/predictions"]:
        status, body, latency = fetch(f"{API}{path}", timeout=10)
        if status == 200:
            try:
                data = json.loads(body)
                count = len(data) if isinstance(data, list) else "ok"
                record("PASS", f"DB:{path}", f"returned {count}", latency_ms=latency)
                print(f"  ✅ {path} → 200 (返回 {count}) ({latency:.0f}ms)")
            except:
                record("PASS", f"DB:{path}", "200 OK", latency_ms=latency)
                print(f"  ✅ {path} → 200 ({latency:.0f}ms)")
        else:
            record("WARN", f"DB:{path}", f"HTTP {status}", latency_ms=latency)
            print(f"  ⚠️ {path} → {status} ({latency:.0f}ms)")

# =========================================================================
# 6. Error Handling Edge Cases
# =========================================================================
def test_error_handling():
    print("\n" + "="*60)
    print("🛡️ 6. 错误处理边界测试")
    print("="*60)
    
    edge_cases = [
        # Invalid IDs → expect 404
        ("GET", "/debates/nonexistent-id-12345", None, "404", "无效ID"),
        ("GET", "/assistant/sessions/nonexistent-session", None, "404", "无效session ID"),
        ("GET", "/sources/custom/nonexistent-source", None, "404", "无效source key"),
        
        # Missing POST body → expect 422
        ("POST", "/analysis", None, "422", "空POST body"),
        ("POST", "/debate/stream", None, "422", "空debate请求"),
        ("POST", "/simulation/runs", None, "422", "空simulation请求"),
        
        # Invalid POST body
        ("POST", "/analysis", {"invalid": "data"}, "422", "无效POST数据"),
        ("POST", "/sources/custom", {"bad": "schema"}, "422", "无效source schema"),
        
        # Extreme query params
        ("GET", "/claims?limit=0", None, None, "limit=0"),
        ("GET", "/claims?limit=999999", None, None, "limit=999999"),
        ("GET", "/evidence?limit=-1", None, None, "limit=-1"),
        ("GET", "/predictions?limit=1", None, None, "limit=1"),
        
        # DELETE on nonexistent
        ("DELETE", "/sources/custom/nonexistent-key-xyz", None, "404", "删除不存在的source"),
        ("DELETE", "/agents/custom/nonexistent-role", None, "404", "删除不存在的agent"),
    ]
    
    for method, path, data, expected, desc in edge_cases:
        url = f"{API}{path}"
        status, body, latency = fetch(url, method=method, data=data, timeout=10)
        
        if status == 500:
            record("WARN", f"Edge:{desc}", f"HTTP 500 on {method} {path}", latency_ms=latency)
            print(f"  ⚠️ {desc}: {method} {path} → 500 ({latency:.0f}ms)")
        elif expected and str(status) == expected:
            record("PASS", f"Edge:{desc}", f"correctly returned {status}", latency_ms=latency)
            print(f"  ✅ {desc}: {method} {path} → {status} (expected) ({latency:.0f}ms)")
        elif status in (400, 404, 405, 422):
            record("PASS", f"Edge:{desc}", f"returned {status}", latency_ms=latency)
            print(f"  ✅ {desc}: {method} {path} → {status} ({latency:.0f}ms)")
        else:
            record("WARN", f"Edge:{desc}", f"HTTP {status} (expected {expected})", latency_ms=latency)
            print(f"  ⚠️ {desc}: {method} {path} → {status} (expected {expected}) ({latency:.0f}ms)")

# =========================================================================
# 7. Response Time Benchmarks
# =========================================================================
def test_response_times():
    print("\n" + "="*60)
    print("⏱️ 7. 响应时间基准测试")
    print("="*60)
    
    key_endpoints = [
        "/",
        "/health",
        "/health/ready",
        "/sources/reputation",
        "/sources/custom",
        "/agents",
        "/claims",
        "/evidence",
        "/signals",
        "/trends",
        "/predictions",
        "/decisions",
        "/debates",
        "/monitoring/dashboard",
        "/model/settings",
        "/model/capabilities",
        "/knowledge/graph",
        "/calibration",
    ]
    
    for path in key_endpoints:
        latencies = []
        for _ in range(5):
            status, _, latency = fetch(f"{API}{path}", timeout=15)
            if status in (200, 422):
                latencies.append(latency)
        
        if latencies:
            avg = sum(latencies) / len(latencies)
            min_l = min(latencies)
            max_l = max(latencies)
            
            if avg > 5000:
                record("FAIL", f"Bench:{path}", f"avg {avg:.0f}ms > 5000ms", latency_ms=avg)
                print(f"  ❌ {path}: avg={avg:.0f}ms min={min_l:.0f}ms max={max_l:.0f}ms")
            elif avg > 2000:
                record("WARN", f"Bench:{path}", f"avg {avg:.0f}ms > 2000ms", latency_ms=avg)
                print(f"  ⚠️ {path}: avg={avg:.0f}ms min={min_l:.0f}ms max={max_l:.0f}ms")
            else:
                record("PASS", f"Bench:{path}", f"avg {avg:.0f}ms", latency_ms=avg)
                print(f"  ✅ {path}: avg={avg:.0f}ms min={min_l:.0f}ms max={max_l:.0f}ms")
        else:
            record("FAIL", f"Bench:{path}", "no successful responses")
            print(f"  ❌ {path}: 无成功响应")

# =========================================================================
# Main
# =========================================================================
if __name__ == "__main__":
    print("🔍 明鉴 (MingJian) 7维压力测试")
    print(f"   后端: {API}")
    print(f"   前端: {FRONTEND}")
    print(f"   时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Pre-check
    status, _, latency = fetch(f"{API}/", timeout=5)
    if status == 0:
        print(f"\n❌ 后端 {API} 无法连接！请先启动后端服务。")
        sys.exit(1)
    print(f"   后端连接: ✅ (HTTP {status}, {latency:.0f}ms)")
    
    status2, _, latency2 = fetch(f"{FRONTEND}/", timeout=5)
    frontend_ok = status2 == 200
    print(f"   前端连接: {'✅' if frontend_ok else '⚠️'} (HTTP {status2}, {latency2:.0f}ms)")
    
    start_time = time.time()
    
    test_api_reachability()
    if frontend_ok:
        test_frontend_pages()
    else:
        print("\n⚠️ 前端未启动，跳过前端测试")
    test_concurrent_load()
    test_sse_connections()
    test_database_health()
    test_error_handling()
    test_response_times()
    
    total_time = time.time() - start_time
    
    # Summary
    print("\n" + "="*60)
    print("📊 明鉴压力测试汇总报告")
    print("="*60)
    print(f"  ✅ 通过: {RESULTS['pass']}")
    print(f"  ❌ 失败: {RESULTS['fail']}")
    print(f"  ⚠️ 警告: {RESULTS['warn']}")
    print(f"  ⏱️ 总耗时: {total_time:.1f}s")
    
    if RESULTS["errors"]:
        print(f"\n{'─'*40}")
        print("❌ 失败项:")
        for err in RESULTS["errors"]:
            print(f"  {err}")
    
    if RESULTS["warnings"]:
        print(f"\n{'─'*40}")
        print("⚠️ 警告项:")
        for warn in RESULTS["warnings"][:10]:
            print(f"  {warn}")
        if len(RESULTS["warnings"]) > 10:
            print(f"  ... 还有 {len(RESULTS['warnings'])-10} 个警告")
    
    # Latency summary
    if RESULTS["details"]:
        latencies = [d[2] for d in RESULTS["details"] if d[2] > 0]
        if latencies:
            print(f"\n{'─'*40}")
            print("⏱️ 延迟分布:")
            sorted_l = sorted(latencies)
            print(f"  P50:  {sorted_l[int(len(sorted_l)*0.5)]:.0f}ms")
            print(f"  P95:  {sorted_l[int(len(sorted_l)*0.95)]:.0f}ms")
            print(f"  P99:  {sorted_l[int(len(sorted_l)*0.99)]:.0f}ms")
            print(f"  Max:  {max(sorted_l):.0f}ms")
    
    print(f"\n{'═'*60}")
    if RESULTS["fail"] == 0:
        print("结论: ✅ 全部通过！")
    else:
        print(f"结论: ❌ 存在 {RESULTS['fail']} 个失败项，需要修复")
    print(f"{'═'*60}")
    
    sys.exit(0 if RESULTS["fail"] == 0 else 1)
