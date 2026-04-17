# Free Proxy Generator & Rotating Proxy API

A self-hosted rotating proxy service built entirely on **free public proxies**.
It harvests, validates, scores, and continuously refreshes a pool of working HTTP/SOCKS proxies,
then exposes them through a local REST API and a standard HTTP forward-proxy tunnel — so any
scraping project can plug in with zero code changes.

---

## Table of Contents

1. [What This Is](#1-what-this-is)
2. [Architecture](#2-architecture)
3. [Requirements & Installation](#3-requirements--installation)
4. [Quick Start (30 seconds)](#4-quick-start-30-seconds)
5. [Tool Reference](#5-tool-reference)
   - [Proxy-api.py — API Server](#proxy-apipy--api-server--main-tool)
   - [Live-proxies.py — Live Terminal](#live-proxiespy--live-terminal)
   - [Proxy-harvester.py — Headless Harvester](#proxy-harvesterpy--headless-harvester)
   - [Test-proxy.py — Pool Tester](#test-proxypy--pool-tester)
6. [API Endpoint Reference](#6-api-endpoint-reference)
7. [Using the Proxy Tunnel](#7-using-the-proxy-tunnel)
8. [Filtering Proxies](#8-filtering-proxies)
9. [Sticky Sessions](#9-sticky-sessions)
10. [Per-Proxy Cooldown / Rate Limiting](#10-per-proxy-cooldown--rate-limiting)
11. [Integration Examples](#11-integration-examples)
12. [Scoring System](#12-scoring-system)
13. [Anonymity Levels](#13-anonymity-levels)
14. [Output File Structure](#14-output-file-structure)
15. [CLI Flag Reference](#15-cli-flag-reference)
16. [Limitations & Best Practices](#16-limitations--best-practices)

---

## 1. What This Is

This project automatically:

- **Harvests** proxy candidates from **44 public sources** (GitHub repos, APIs) covering HTTP, SOCKS4, and SOCKS5
- **Validates** each candidate by actually connecting through it and checking the response
- **Scores** every proxy on a composite metric: success rate, speed, freshness, stability
- **Enriches** working proxies with anonymity level (elite / anonymous / transparent) and country code
- **Exposes** the live pool through a REST API and a standard HTTP forward-proxy tunnel
- **Auto-rotates** — every request goes through the best available proxy, with smart fallback

You run one command, and your existing `requests.get(url, proxies=...)` code just works.

---

## 2. Architecture

```
proxy_core.py          — Core engine (shared by all tools)
│   ProxyHarvester     — Fetches sources, validates, scores, enriches, saves
│   ProxyRecord        — Per-proxy state: score, anonymity, country, cooldown
│   probe_proxy()      — Async connectivity check through a proxy
│   check_proxy_anonymity() — Detects elite / anonymous / transparent
│   lookup_proxy_country()  — ISO-2 country code via ip-api.com
│
├── Proxy-api.py       — REST API server + forward-proxy tunnel  ← main tool
├── Live-proxies.py    — Live terminal window of working proxies
├── Proxy-harvester.py — Headless continuous harvester (no display)
└── Test-proxy.py      — One-shot pool tester / URL fetcher
```

**Data flow inside `Proxy-api.py`:**

```
Sources (44 URLs)
      │
      ▼ fetch every 120s
  ProxyHarvester.collect_candidates()
      │
      ▼ validate concurrently (120 workers)
  ProxyHarvester.verify_proxies()      → ProxyRecord.record_success/failure()
      │
      ▼ enrich (25/cycle, background)
  check_proxy_anonymity()  →  record.anonymity = "elite" | "anonymous" | "transparent"
  lookup_proxy_country()   →  record.country   = "US" | "DE" | ...
      │
      ▼ ranked by score
  active_proxies pool (JSON file)
      │
      ├── GET /next         → round-robin
      ├── GET /random       → random pick
      ├── GET /proxies      → filtered list
      ├── GET/POST /fetch   → fetch URL through pool, return JSON
      ├── GET/POST /proxy   → fetch URL through pool, return raw response
      └── TCP :5226         → standard CONNECT forward-proxy tunnel
```

---

## 3. Requirements & Installation

**Python 3.10 or newer** is required.

```bash
# Clone or download the project, then:
cd "Proxy Generator"

# Create virtual environment (recommended)
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Dependencies:**
- `aiohttp` — async HTTP client/server
- `aiohttp-socks` — SOCKS4/5 proxy support for aiohttp
- `requests` — used in example code (not required by the server itself)
- `rich` — optional, makes the terminal display much nicer

---

## 4. Quick Start (30 seconds)

### Option A — Full API server (recommended)

```bash
python Proxy-api.py
```

Wait ~2 minutes for the first collection cycle. Then:

```bash
# Check pool status
curl http://127.0.0.1:8080/status

# Fetch any URL through a rotating proxy
curl "http://127.0.0.1:8080/proxy?url=https://httpbin.org/ip"

# Get next proxy in round-robin rotation
curl http://127.0.0.1:8080/next
```

### Option B — Standard forward-proxy tunnel (drop-in replacement)

```bash
python Proxy-api.py --tunnel-port 5226
```

Then in your Python scraper:

```python
import requests

proxies = {
    "http":  "http://127.0.0.1:5226",
    "https": "http://127.0.0.1:5226",
}
r = requests.get("https://httpbin.org/ip", proxies=proxies)
print(r.json())  # shows the proxy's IP, not yours
```

### Option C — Live terminal display

```bash
python Live-proxies.py
```

Shows a live table of working proxies that refreshes every 5 seconds.

### Option D — Windows one-click launcher

```bat
Start-Live-Proxies.bat
```

Starts both the live terminal window and the API server at once.

---

## 5. Tool Reference

### `Proxy-api.py` — API Server ← main tool

The primary tool. Runs a REST API server that maintains a live rotating proxy pool and
serves requests through it. Also runs the forward-proxy tunnel on port 5226.

```bash
python Proxy-api.py [options]
```

**Most useful flags:**

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | API bind address. Use `0.0.0.0` for LAN access |
| `--port` | `8080` | API HTTP port |
| `--tunnel-port` | `5226` | Forward-proxy tunnel port. Use `0` to disable |
| `--tunnel-host` | `127.0.0.1` | Tunnel bind address |
| `--warmup` | off | Block startup until first full pool cycle completes |
| `--max-concurrent` | `120` | Concurrent proxy checks and source fetches |
| `--update-interval` | `120` | Seconds between full source refresh cycles |
| `--verify-interval` | `60` | Seconds between active proxy re-checks |
| `--max-candidates` | `1000` | Max proxies to validate per source cycle |
| `--min-success-rate` | `0.35` | Drop proxies below this success rate |
| `--max-failures` | `3` | Consecutive failures before proxy removal |
| `--stale-after` | `1800` | Seconds since last success before proxy is dropped |
| `--max-response-time` | `12.0` | Drop proxies slower than this (seconds) |
| `--request-timeout` | `20.0` | Timeout for target URL fetches via `/fetch` or `/proxy` |
| `--proxy-delay` | `0.5` | Seconds to wait between proxy attempts on failure |
| `--no-rotate-ua` | — | Disable random User-Agent rotation |
| `--no-shuffle-proxies` | — | Use top-ranked proxies in order instead of shuffling |
| `--source-file FILE` | — | Extra source URLs, one per line |
| `--probe-url URL` | — | Additional probe URL (can repeat) |

**Example — strict, fast pool, open to LAN:**

```bash
python Proxy-api.py \
  --host 0.0.0.0 \
  --port 8080 \
  --tunnel-port 5226 \
  --warmup \
  --min-success-rate 0.50 \
  --max-response-time 8 \
  --max-failures 2 \
  --max-candidates 400
```

---

### `Live-proxies.py` — Live Terminal

Runs the harvester and shows a live updating table of working proxies in the terminal.
Each run creates its own timestamped session folder under `output/`.

```bash
python Live-proxies.py [options]
```

**Session folder structure:**

```
output/
  latest_session.txt          ← path to most recent session
  proxies_2026-04-17-10-30-00/
    active_proxies.json       ← full ranked pool (all active proxies)
    working_proxies.txt       ← plain list, one proxy per line
    working_proxies.json      ← filtered live proxies with metadata
    session_info.json         ← session metadata and file paths
```

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--limit` | `100` | Max proxies to show and export |
| `--min-score` | `0.0` | Only show proxies above this score |
| `--plain` | off | Plain list instead of rich table |
| `--once` | off | Run one cycle then exit |
| `--refresh-delay` | `5.0` | Seconds between screen refreshes |
| `--output-root` | `output` | Root folder for session directories |
| `--session-prefix` | `proxies` | Prefix for session folder names |

**Useful example — export top 50 fast proxies:**

```bash
python Live-proxies.py --limit 50 --min-score 0.50 --max-response-time 5
```

Your scraper can then read `output/latest_session.txt` → load that path → read `working_proxies.txt`
for a fresh list of working proxies without running the API.

---

### `Proxy-harvester.py` — Headless Harvester

Collects and validates proxies continuously without a display. Writes to `active_proxies.json`.
Use this when you want the pool file but don't need the API or live display.

```bash
python Proxy-harvester.py [options]
```

**Key flags:**

| Flag | Default | Description |
|---|---|---|
| `--once` | off | Single cycle then exit |
| `--output` | `active_proxies.json` | Output file path |
| `--max-concurrent` | `200` | Concurrent connections |
| `--max-candidates` | `3000` | Candidates per source cycle |
| `--verify-batch-size` | `200` | Active proxies re-checked per cycle |

**Quick one-shot run:**

```bash
python Proxy-harvester.py --once
```

---

### `Test-proxy.py` — Pool Tester

Re-tests saved proxies or fetches a specific URL through the saved pool.
Does not run a server — it's a one-shot command.

```bash
# Re-test the saved pool
python Test-proxy.py --limit 50

# Fetch a specific URL through rotating proxies
python Test-proxy.py --target-url "https://example.com" --max-attempts 15

# Save currently working proxies to a separate file
python Test-proxy.py --limit 100 --save-working verified_now.json

# Fetch a page and save its HTML
python Test-proxy.py --target-url "https://example.com" --output-body page.html
```

---

## 6. API Endpoint Reference

All endpoints return JSON. The API server runs on `http://127.0.0.1:8080` by default.

---

### `GET /status` or `GET /health`

Returns current pool status, active proxy count, best proxy, progress state.

```bash
curl http://127.0.0.1:8080/status
```

```json
{
  "ok": true,
  "active_proxies": 87,
  "known_records": 412,
  "best_proxy": "http://1.2.3.4:8080",
  "last_refresh_at": "2026-04-17T10:30:00+00:00",
  "sources_count": 44,
  "progress": { "phase": "cycle_complete", "active_now": 87 }
}
```

---

### `GET /stats`

Detailed breakdown of the active pool by protocol, country, and anonymity level.

```bash
curl http://127.0.0.1:8080/stats
```

```json
{
  "ok": true,
  "total_active": 87,
  "by_protocol": { "http": 62, "socks5": 18, "socks4": 7 },
  "by_country": { "US": 12, "DE": 8, "FR": 6, "IN": 5 },
  "by_anonymity": { "elite": 34, "anonymous": 28, "transparent": 8, "unknown": 17 },
  "avg_score": 0.6241,
  "avg_response_time": 4.821,
  "enriched_count": 70,
  "geolocated_count": 65
}
```

> **Note:** `enriched_count` and `geolocated_count` grow over time as the background
> enrichment process processes 25 proxies per cycle. After a few cycles, most active proxies
> will have both fields populated.

---

### `GET /proxies`

Returns a ranked list of active proxies. Supports filters.

```bash
# All active proxies (top 50)
curl http://127.0.0.1:8080/proxies

# Only elite HTTP proxies from the US
curl "http://127.0.0.1:8080/proxies?protocol=http&anonymity=elite&country=US"

# Top 20 SOCKS5 proxies with score above 0.5
curl "http://127.0.0.1:8080/proxies?protocol=socks5&min_score=0.5&limit=20"
```

**Query parameters:**

| Parameter | Example | Description |
|---|---|---|
| `limit` | `50` | Max results returned |
| `min_score` | `0.4` | Minimum composite score |
| `protocol` | `http`, `socks5`, `socks4` | Filter by protocol |
| `country` | `US`, `DE`, `IN` | ISO-2 country code filter |
| `anonymity` | `elite`, `anonymous`, `transparent` | Anonymity level filter |

Each proxy object in the response:

```json
{
  "proxy": "http://1.2.3.4:8080",
  "protocol": "http",
  "country": "US",
  "anonymity": "elite",
  "score": 0.7812,
  "success_rate": 0.857,
  "avg_response_time": 2.34,
  "total_checks": 14,
  "successful_checks": 12,
  "consecutive_failures": 0,
  "last_origin": "1.2.3.4"
}
```

---

### `GET /next`

**Round-robin rotation** — returns the next proxy in a rotating sequence.
Every call advances the internal index by one. Use this in a scraping loop
for even distribution across the pool.

```bash
curl http://127.0.0.1:8080/next

# With filters
curl "http://127.0.0.1:8080/next?protocol=socks5&anonymity=elite"

# With cooldown: skip proxies used in the last 30 seconds
curl "http://127.0.0.1:8080/next?skip_cooldown=30"
```

**Query parameters:**

| Parameter | Example | Description |
|---|---|---|
| `protocol` | `socks5` | Only return this protocol |
| `country` | `US` | Only return proxies from this country |
| `anonymity` | `elite` | Only return this anonymity level |
| `min_score` | `0.5` | Minimum score threshold |
| `skip_cooldown` | `30` | Skip proxies used within this many seconds |

**Response:**

```json
{
  "ok": true,
  "proxy": "http://5.6.7.8:3128",
  "protocol": "http",
  "country": "DE",
  "anonymity": "elite",
  "score": 0.8234,
  "avg_response_time": 1.92,
  "success_rate": 0.9
}
```

---

### `GET /random`

Returns a **random** proxy from the active pool (optionally filtered).
Unlike `/next`, this does not advance a rotation index — each call is independent.

```bash
curl http://127.0.0.1:8080/random

# Random elite proxy
curl "http://127.0.0.1:8080/random?anonymity=elite"
```

Same query parameters and response format as `/next`.

---

### `GET /proxy?url=<target>`

Fetches a target URL through the proxy pool and returns the **raw response** (body as-is,
headers forwarded). Behaves like a transparent proxy.

```bash
curl "http://127.0.0.1:8080/proxy?url=https://httpbin.org/ip"
curl "http://127.0.0.1:8080/proxy?url=https://example.com"
```

**Query parameters:**

| Parameter | Default | Description |
|---|---|---|
| `url` | required | Target URL (must be http or https) |
| `max_attempts` | `10` | How many proxies to try before giving up |
| `timeout` | server default | Per-attempt timeout in seconds |
| `min_score` | `0.0` | Minimum proxy score |
| `pool_limit` | `50` | How many proxies from the pool to consider |
| `allow_redirects` | `true` | Follow HTTP redirects |
| `session_id` | — | Sticky session ID (see section 10) |
| `min_proxy_interval` | `0` | Cooldown seconds per proxy |

**Response headers added:**
- `X-Proxy-Used` — which proxy was used
- `X-Proxy-Score` — that proxy's score
- `X-Proxy-Attempts` — how many proxies were tried
- `X-Final-URL` — URL after redirects

---

### `POST /fetch`

Fetches a target URL through the proxy pool and returns a **JSON wrapper** with body,
status code, headers, and attempt details. Best for programmatic use.

```bash
curl -X POST http://127.0.0.1:8080/fetch \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://httpbin.org/ip",
    "max_attempts": 10,
    "min_score": 0.4
  }'
```

**POST body fields (all optional except `url`):**

| Field | Default | Description |
|---|---|---|
| `url` | required | Target URL |
| `method` | `GET` | HTTP method |
| `headers` | `{}` | Extra request headers |
| `body` | `null` | Request body (string) |
| `timeout` | server default | Per-attempt timeout |
| `max_attempts` | `10` | Proxy retry limit |
| `expected_status` | `null` | Retry if status doesn't match this |
| `pool_limit` | `50` | Pool size to sample from |
| `min_score` | `0.0` | Minimum proxy score |
| `allow_redirects` | `true` | Follow redirects |
| `session_id` | `null` | Sticky session (see section 10) |
| `min_proxy_interval` | `0` | Per-proxy cooldown seconds |

**Response:**

```json
{
  "ok": true,
  "proxy": "http://1.2.3.4:8080",
  "proxy_score": 0.7812,
  "proxy_country": "US",
  "proxy_anonymity": "elite",
  "proxy_protocol": "http",
  "status_code": 200,
  "reason": "OK",
  "final_url": "https://httpbin.org/ip",
  "headers": { "Content-Type": "application/json", ... },
  "body": "{\"origin\": \"1.2.3.4\"}",
  "attempts": [
    { "attempt": 1, "proxy": "http://1.2.3.4:8080", "status_code": 200 }
  ]
}
```

---

### `GET /tunnel-status`

Returns the status and connection stats for the forward-proxy tunnel.

```bash
curl http://127.0.0.1:8080/tunnel-status
```

```json
{
  "ok": true,
  "tunnel_enabled": true,
  "tunnel_url": "http://127.0.0.1:5226",
  "tunnel_port": 5226,
  "max_attempts": 5,
  "stats": {
    "total_requests": 145,
    "connect_requests": 98,
    "http_requests": 47,
    "successful": 132,
    "failed": 13
  }
}
```

---

## 7. Using the Proxy Tunnel

The tunnel on port **5226** is a standard HTTP forward proxy that supports both plain HTTP
and HTTPS (via CONNECT). It automatically routes your traffic through the best available
upstream proxy from the pool, with retry on failure.

**Start with tunnel enabled:**

```bash
python Proxy-api.py --tunnel-port 5226
```

**Python `requests`:**

```python
import requests

PROXY = "http://127.0.0.1:5226"
proxies = {"http": PROXY, "https": PROXY}

r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=30)
print(r.json())
```

**Python `httpx`:**

```python
import httpx

with httpx.Client(proxy="http://127.0.0.1:5226") as client:
    r = client.get("https://httpbin.org/ip")
    print(r.json())
```

**curl:**

```bash
curl -x http://127.0.0.1:5226 https://httpbin.org/ip
curl -x http://127.0.0.1:5226 https://example.com -L
```

**Scrapy** (`settings.py`):

```python
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 110,
}
HTTP_PROXY = "http://127.0.0.1:5226"
HTTPS_PROXY = "http://127.0.0.1:5226"
```

**LAN access** — start with `--tunnel-host 0.0.0.0` and use your machine's LAN IP from
other devices on the same network:

```bash
python Proxy-api.py --tunnel-host 0.0.0.0 --tunnel-port 5226
# Then from another device:
curl -x http://192.168.1.10:5226 https://httpbin.org/ip
```

---

## 8. Filtering Proxies

All filter parameters work on `/proxies`, `/next`, `/random`, and `/fetch` (POST body).

### By Protocol

```bash
# HTTP only
curl "http://127.0.0.1:8080/next?protocol=http"

# SOCKS5 only
curl "http://127.0.0.1:8080/next?protocol=socks5"

# SOCKS4 only
curl "http://127.0.0.1:8080/next?protocol=socks4"
```

### By Country

Use ISO 3166-1 alpha-2 country codes. Country data is populated by the background
enrichment process (takes a few minutes after startup).

```bash
# US proxies only
curl "http://127.0.0.1:8080/proxies?country=US"

# German SOCKS5 proxies
curl "http://127.0.0.1:8080/next?country=DE&protocol=socks5"
```

### By Anonymity Level

```bash
# Only elite proxies (don't reveal you're using a proxy)
curl "http://127.0.0.1:8080/proxies?anonymity=elite"

# Elite proxies from a specific country
curl "http://127.0.0.1:8080/next?anonymity=elite&country=US"
```

### By Minimum Score

Score ranges from 0.0 to 1.0. Higher is better.

```bash
# Only high-quality proxies
curl "http://127.0.0.1:8080/proxies?min_score=0.6"
```

### Combining Filters

All filters can be combined:

```bash
curl "http://127.0.0.1:8080/proxies?protocol=http&anonymity=elite&country=US&min_score=0.5&limit=10"
```

---

## 9. Sticky Sessions

A sticky session pins a specific proxy to a `session_id` string so that multiple
requests in the same "session" always go through the same upstream proxy.

**How it works:**
1. First request with a `session_id` uses the normal rotation to pick a proxy
2. That proxy is stored: `session_id → proxy`
3. All subsequent requests with the same `session_id` try that proxy first
4. If the preferred proxy is dead/removed, the system falls back and picks a new one
5. The new proxy is then remembered for that session

**Via `/fetch` POST:**

```python
import requests

SESSION = "user_account_42"

def scrape(url):
    r = requests.post("http://127.0.0.1:8080/fetch", json={
        "url": url,
        "session_id": SESSION,
        "max_attempts": 5,
    })
    return r.json()

# Both calls will use the same upstream proxy
page1 = scrape("https://example.com/login")
page2 = scrape("https://example.com/dashboard")  # same proxy as page1
```

**Via `/proxy` GET:**

```bash
curl "http://127.0.0.1:8080/proxy?url=https://example.com&session_id=my_session"
```

**Session memory limit:** The server stores up to 10,000 session mappings. If this limit
is hit (e.g., in very long-running servers), the session map resets automatically.

---

## 10. Per-Proxy Cooldown / Rate Limiting

`min_proxy_interval` sets the minimum seconds that must pass before the same proxy
is used again. This prevents a single proxy from being hammered too quickly,
which reduces the chance of getting banned.

```python
import requests

# Each proxy can only be reused after 60 seconds
r = requests.post("http://127.0.0.1:8080/fetch", json={
    "url": "https://target-site.com/product/123",
    "min_proxy_interval": 60,
    "max_attempts": 15,
})
```

You can also use the `skip_cooldown` parameter on `/next` to avoid proxies used recently:

```bash
# Skip any proxy used in the last 30 seconds
curl "http://127.0.0.1:8080/next?skip_cooldown=30"
```

---

## 11. Integration Examples

### Simple rotating requests

```python
import requests

def fetch(url, retries=3):
    for _ in range(retries):
        try:
            r = requests.post("http://127.0.0.1:8080/fetch", json={
                "url": url,
                "max_attempts": 10,
                "timeout": 20,
                "min_score": 0.4,
            }, timeout=60)
            data = r.json()
            if data.get("ok"):
                return data["body"]
        except Exception:
            pass
    return None

html = fetch("https://example.com/products")
```

---

### Using the tunnel with requests (drop-in, zero code change)

```python
import requests

session = requests.Session()
session.proxies = {
    "http":  "http://127.0.0.1:5226",
    "https": "http://127.0.0.1:5226",
}
session.timeout = 30

r = session.get("https://httpbin.org/ip")
print(r.json())  # proxy IP, not your real IP
```

---

### Scrapy spider

```python
# In your spider or middleware:
import requests

class ProxyMiddleware:
    PROXY = "http://127.0.0.1:5226"

    def process_request(self, request, spider):
        request.meta["proxy"] = self.PROXY
```

Or in `settings.py`:

```python
HTTP_PROXY  = "http://127.0.0.1:5226"
HTTPS_PROXY = "http://127.0.0.1:5226"
DOWNLOADER_MIDDLEWARES = {
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 110,
}
RETRY_TIMES = 5
```

---

### Elite-only scraping (avoid detection)

```python
import requests

def get_elite_proxy():
    r = requests.get("http://127.0.0.1:8080/next?anonymity=elite&min_score=0.5")
    return r.json().get("proxy")

proxy_url = get_elite_proxy()
if proxy_url:
    r = requests.get(
        "https://target-site.com",
        proxies={"http": proxy_url, "https": proxy_url},
        timeout=20,
    )
```

---

### Scraping with sticky sessions (login flows)

```python
import requests

API = "http://127.0.0.1:8080/fetch"

def fetch_with_session(url, session_id, method="GET", data=None):
    payload = {
        "url": url,
        "method": method,
        "session_id": session_id,
        "max_attempts": 8,
    }
    if data:
        payload["body"] = data
    r = requests.post(API, json=payload, timeout=60)
    return r.json()

# Login and dashboard will use the same proxy
login_resp  = fetch_with_session("https://site.com/api/login",    "session_A", "POST", '{"user":"x"}')
dash_resp   = fetch_with_session("https://site.com/api/dashboard", "session_A")
```

---

### Reading the pool file directly (no server)

```python
import json
from pathlib import Path

# After running Live-proxies.py at least once:
session_dir = Path("output/latest_session.txt").read_text().strip()
proxies_txt = Path(session_dir) / "working_proxies.txt"

proxy_list = proxies_txt.read_text().splitlines()
print(f"Available: {len(proxy_list)} proxies")
print("First proxy:", proxy_list[0])
```

---

### Checking pool stats programmatically

```python
import requests

stats = requests.get("http://127.0.0.1:8080/stats").json()
print(f"Total active: {stats['total_active']}")
print(f"Elite proxies: {stats['by_anonymity'].get('elite', 0)}")
print(f"US proxies: {stats['by_country'].get('US', 0)}")
print(f"SOCKS5: {stats['by_protocol'].get('socks5', 0)}")
print(f"Avg score: {stats['avg_score']:.3f}")
print(f"Avg RTT: {stats['avg_response_time']:.2f}s")
```

---

## 12. Scoring System

Every proxy is assigned a composite **score from 0.0 to 1.0**. The score is recalculated
after every check. Higher score = better proxy.

```
score = (success_rate × 0.50)
      + (speed_score  × 0.25)
      + (freshness    × 0.15)
      + (stability    × 0.10)
```

| Component | Weight | What it measures |
|---|---|---|
| **Success rate** | 50% | `successful_checks / total_checks` — reliability over all time |
| **Speed score** | 25% | `1 - (avg_rtt / max_response_time)` — lower RTT = higher score |
| **Freshness** | 15% | How recently the proxy had a successful check |
| **Stability** | 10% | Penalizes consecutive failures |

**A proxy is dropped from the active pool when:**
- It has no successful checks ever
- It has ≥ `max_consecutive_failures` failures in a row (default: 3)
- Its success rate drops below `min_success_rate` (default: 0.35) after 3+ checks
- Its average response time exceeds `max_response_time` (default: 12s)
- It hasn't had a success in `stale_after` seconds (default: 1800 = 30 minutes)

---

## 13. Anonymity Levels

Anonymity is detected by routing a request through the proxy to `httpbin.org/headers`
and inspecting which headers the server received.

| Level | What the target server sees | Good for |
|---|---|---|
| **elite** | No proxy headers at all. Looks like a regular browser. | Bypassing bot detection, sites that block proxies |
| **anonymous** | Has `Via` or `Proxy-Connection` header but hides your real IP | General scraping |
| **transparent** | Sends `X-Forwarded-For` with a real IP | Only for non-sensitive scraping |
| **unknown** | Not yet checked (enrichment pending) | Treat as untrusted |

**For scraping sites with anti-bot protection, always use `anonymity=elite`.**

```bash
# Only elite proxies
curl "http://127.0.0.1:8080/next?anonymity=elite"
```

Note: SOCKS proxies cannot be tested for anonymity through the core aiohttp session,
so they always show `unknown` until a future improvement.

---

## 14. Output File Structure

### `active_proxies.json` (saved every 15 seconds)

```json
{
  "updated_at": "2026-04-17T10:30:00+00:00",
  "count": 87,
  "summary": {
    "known_records": 412,
    "active_records": 87,
    "sources": 44
  },
  "config": { ... },
  "sources": [
    { "url": "https://...", "last_count": 312, "last_error": "" }
  ],
  "proxies": [
    {
      "proxy": "http://1.2.3.4:8080",
      "protocol": "http",
      "country": "US",
      "anonymity": "elite",
      "score": 0.8234,
      "success_rate": 0.857143,
      "avg_response_time": 2.34,
      "total_checks": 14,
      "successful_checks": 12,
      "consecutive_failures": 0,
      "response_times": [1.9, 2.1, 2.5, 2.8],
      "source_urls": ["https://github.com/..."],
      "last_probe_url": "http://httpbin.org/ip",
      "last_origin": "1.2.3.4",
      "last_error": "",
      "first_seen": "2026-04-17T10:00:00+00:00",
      "last_seen_success": "2026-04-17T10:29:45+00:00",
      "last_checked": "2026-04-17T10:29:45+00:00"
    }
  ]
}
```

### `working_proxies.txt` (Live-proxies.py only)

Plain text, one proxy per line. Your scraper can read this directly.

```
http://1.2.3.4:8080
socks5://5.6.7.8:1080
http://9.10.11.12:3128
```

### `session_info.json`

```json
{
  "session_dir": "C:/..../output/proxies_2026-04-17-10-30-00",
  "updated_at": "2026-04-17T10:30:00+00:00",
  "active_total": 87,
  "files": {
    "active_pool_json": "...active_proxies.json",
    "working_txt":      "...working_proxies.txt",
    "working_json":     "...working_proxies.json"
  },
  "sources_count": 44
}
```

---

## 15. CLI Flag Reference

### Common flags (shared across tools)

| Flag | Default | Description |
|---|---|---|
| `--max-concurrent` | varies | Max simultaneous connections |
| `--fetch-timeout` | `8-10` | Timeout fetching source lists (seconds) |
| `--verify-timeout` | `8-10` | Timeout per proxy check (seconds) |
| `--update-interval` | `120` | Seconds between source re-fetch cycles |
| `--verify-interval` | `60` | Seconds between active proxy re-checks |
| `--auto-save-interval` | `15` | Minimum seconds between JSON writes |
| `--max-candidates` | varies | Max proxies to validate per cycle |
| `--verify-batch-size` | varies | Active proxies re-checked per cycle |
| `--min-success-rate` | `0.35` | Drop threshold |
| `--max-failures` | `3` | Consecutive failure limit |
| `--stale-after` | `1800` | Staleness threshold (seconds) |
| `--max-response-time` | `12.0` | Speed cutoff (seconds) |
| `--probe-url URL` | — | Extra validation endpoint (repeatable) |
| `--source-file FILE` | — | File with extra source URLs |

### Proxy-api.py only

| Flag | Default | Description |
|---|---|---|
| `--host` | `127.0.0.1` | API bind host |
| `--port` | `8080` | API bind port |
| `--tunnel-port` | `5226` | Tunnel port (`0` = disabled) |
| `--tunnel-host` | `127.0.0.1` | Tunnel bind host |
| `--tunnel-max-attempts` | `5` | Max proxies tried per tunnel request |
| `--tunnel-relay-timeout` | `120.0` | Idle timeout for CONNECT relay (seconds) |
| `--request-timeout` | `20.0` | Target URL fetch timeout |
| `--request-concurrency` | `80` | Max simultaneous outbound fetches |
| `--proxy-delay` | `0.5` | Seconds between retry attempts |
| `--warmup` | off | Complete one cycle before accepting requests |
| `--rotate-ua` / `--no-rotate-ua` | on | User-Agent rotation |
| `--no-shuffle-proxies` | — | Use proxies in rank order |
| `--public-base-url` | — | Public URL if exposed via tunnel/domain |
| `--output-root` | `output` | Session folder root |

---

## 16. Limitations & Best Practices

### Honest limitations

- **Free proxies are unreliable.** A proxy that works right now may be dead in 5 minutes.
  Always use `max_attempts ≥ 10` to absorb failures.
- **Country targeting is limited.** Most free proxies are concentrated in a few countries
  (US, DE, IN, BR, CN). Niche countries may have 0 available proxies.
- **No residential proxies.** All proxies are datacenter IPs. Sites with strong anti-bot
  protection (Cloudflare Enterprise, Akamai) may still block them.
- **Anonymity detection takes time.** Right after startup, most proxies show `unknown`.
  Wait 5-10 minutes for enrichment to populate.
- **SOCKS proxy support is partial.** SOCKS proxies are validated and rotated through the
  tunnel and `/fetch` endpoint, but anonymity detection does not work for SOCKS.

### Best practices

1. **Always set `max_attempts ≥ 10`** — free proxies fail often. Give the system room to retry.

2. **Use `min_score ≥ 0.4`** — this filters out the worst proxies that just barely pass validation.

3. **Use `anonymity=elite`** for sites with bot detection. Transparent proxies will almost
   always get blocked.

4. **Use `min_proxy_interval`** for sites that rate-limit per IP. 30-60 seconds is a good start.

5. **Warm up before scraping** — start the server with `--warmup` so the pool is ready
   before your first request.

6. **Do not store sensitive data through free proxies.** Never send passwords, API keys,
   or personal data through a free proxy. Use only for public/anonymous scraping.

7. **Respect the target site's `robots.txt`** and terms of service. Rotate requests slowly.
   Rate-limit to at most 1-2 requests per second per domain.

8. **Run the server continuously.** The pool gets smarter over time — proxies accumulate
   history, scores stabilize, and enrichment data fills in.

9. **For serious production use**, consider a VPS: run the API server there, bind to
   `0.0.0.0`, and connect from your scraper machine over the LAN or via SSH tunnel.

### Recommended startup for scraping

```bash
# Start with warmup, strict quality thresholds, LAN-accessible
python Proxy-api.py \
  --host 0.0.0.0 \
  --warmup \
  --min-success-rate 0.50 \
  --max-response-time 8 \
  --max-failures 2 \
  --max-candidates 400 \
  --verify-batch-size 80 \
  --tunnel-port 5226
```

Wait for `warmup` to complete (usually 2-4 minutes), then start your scraper.
