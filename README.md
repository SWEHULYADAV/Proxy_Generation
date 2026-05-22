# Proxy Generator

Local BrightData-style proxy service for personal use.

Made by Rahul Yadav (SWEHUL Yadav)

## Disclaimer

This project is provided for educational purposes, research, learning, and personal project use only.

Do not use this project for abuse, unauthorized access, illegal scraping, harassment, fraud, privacy violations, service disruption, or any activity that violates the law, a platform's terms, or another party's rights.

If you choose to misuse this project in any way, you are solely responsible for your own actions and any legal, financial, technical, or other consequences that follow.

The author, Rahul Yadav (SWEHUL Yadav), is not responsible for misuse of this project.

This project gives you a local proxy platform that:

- collects free public proxies from many sources
- verifies them and keeps only active working proxies in rotation
- removes failed proxies from live rotation immediately
- retries requests with another active proxy automatically
- exposes both a REST API and a standard HTTP proxy tunnel
- can be used from almost any language, framework, app, SDK, plugin, or automation tool

The core idea is simple:

1. Run the service locally.
2. Get one local proxy URL or one local API URL.
3. Use that in your project the same way you would use a paid proxy provider.

This is a local proxy service first.
Optional browser stealth helpers are included separately for cases where browser-level fingerprint handling matters.

## Quick Summary

Main local endpoints:

- REST API: `http://127.0.0.1:1712`
- Proxy tunnel: `http://127.0.0.1:1909`
- Authenticated tunnel: `http://proxy:YOUR_PROXY_KEY@127.0.0.1:1909`

Main files:

- [Proxy-api.py](</c:/Users/Admin/Desktop/Proxy Generator/Proxy-api.py>) - local API service and HTTP proxy tunnel
- [proxy_core.py](</c:/Users/Admin/Desktop/Proxy Generator/proxy_core.py>) - source collection, validation, scoring, active pool logic
- [Live-proxies.py](</c:/Users/Admin/Desktop/Proxy Generator/Live-proxies.py>) - live proxy monitor window
- [Start-Live-Proxies.bat](</c:/Users/Admin/Desktop/Proxy Generator/Start-Live-Proxies.bat>) - one-click launcher
- [stealth_browser.py](</c:/Users/Admin/Desktop/Proxy Generator/stealth_browser.py>) - optional browser helper
- [requirements.txt](</c:/Users/Admin/Desktop/Proxy Generator/requirements.txt>) - Python dependencies for the project

## What This Project Really Is

Think of this as a local proxy provider running on your machine.

Instead of paying a remote provider and calling their proxy endpoint, you run this locally and point your apps at:

- `http://127.0.0.1:1909` as a normal proxy
- or `http://127.0.0.1:1712/fetch` and `http://127.0.0.1:1712/proxy` as API endpoints

It is designed so that your app does not need to know about hundreds of individual free proxies.
Your app talks only to this local service.
This service handles:

- source collection
- validation
- active-only filtering
- retry and failover
- basic header humanization
- live rotation

## Important Reality Check

This project uses free public proxies.

That means:

- many proxies are unstable
- some proxies die quickly
- some proxies get blocked by target websites
- most free proxies are datacenter proxies, not true residential proxies

So this project can behave like a local proxy provider, but it cannot promise paid-provider reliability.
What it does promise is that inside the local service:

- only working proxies are kept active
- failed proxies are removed from live rotation immediately
- retries move to the next active proxy
- the background verifier can re-add a proxy later if it recovers

## Core Behavior

### Active-only rotation

The service does not blindly use every proxy it finds.

It:

1. collects candidates from many sources
2. verifies them
3. keeps only active working proxies in the live pool
4. rotates requests only through the active pool
5. drops a proxy from live rotation immediately when a real runtime request fails

That last part matters.
This is not just scheduled validation.
If a proxy fails during a real request, it is removed from current live rotation right away.

### Retry and failover

If a request fails:

1. first proxy is tried
2. if it fails or looks blocked, the next active proxy is tried
3. if that fails, the next one is tried
4. the service returns the result if any active proxy succeeds

### Anti-repeat behavior

When alternatives are available, the service avoids reusing the exact same proxy back-to-back.

### Block detection

For REST fetch mode, the service can treat these as failure/block signals and move on:

- `403`
- `429`
- `503`
- common Cloudflare/block markers
- common captcha-page markers

## Architecture

High-level flow:

```text
public proxy sources
    ->
candidate collection
    ->
proxy verification
    ->
active working pool
    ->
local API and local proxy tunnel
    ->
your project
```

Runtime components:

- `proxy_core.py` manages candidates, scores, verification, and active pool state
- `Proxy-api.py` exposes local endpoints and proxy tunnel behavior
- `Live-proxies.py` gives a visual live monitor
- `stealth_browser.py` is optional and only for browser-level use cases

## Installation

### 1. Open the project folder

```bat
cd "C:\Users\Admin\Desktop\Proxy Generator"
```

### 2. Create a virtual environment

```bat
python -m venv venv
```

Requires Python 3.11 or newer.

### 3. Install Python dependencies

```bat
venv\Scripts\pip install -r requirements.txt
```

If you want the optional browser helper to work fully, also run:

```bat
venv\Scripts\pip install -r requirements-browser.txt
venv\Scripts\python -m cloakbrowser install
venv\Scripts\python -m camoufox fetch
venv\Scripts\playwright install chromium
```

### 4. Create your personal local config

After you have already created `venv` and installed the Python dependencies, run:

```bat
Setup-Authenticated-Proxy-Service.bat
```

This script:

- checks that your `venv` already exists
- checks that Python dependencies are already installed
- asks you for your API key and tunnel password on first run
- auto-generates them if you leave the prompts blank
- creates `proxy-service-config.env` if it does not exist
- saves your personal default ports and launch settings

After that, your normal daily launcher becomes:

```bat
Start-Live-Proxies.bat
```

Installed core Python packages:

- `aiohttp`
- `aiohttp-socks`
- `python-socks`
- `requests`
- `rich`

Optional browser-helper packages:

- `cloakbrowser[geoip]`
- `camoufox[geoip]`
- `playwright`

The proxy service itself relies only on the core networking stack.
The browser packages are optional and only needed for `stealth_browser.py`.

## Launch Modes

### Option 1. Run both windows with the batch file

```bat
Start-Live-Proxies.bat
```

This starts:

- live proxy monitor window
- local API service window

By default, the batch file now binds the service to local-only addresses:

- `127.0.0.1:1712`
- `127.0.0.1:1909`

That is the safer default for personal local use.

### Option 2. Run only the API service

```bat
Start-Live-Proxies.bat api
```

### Option 3. Run only the live monitor

```bat
Start-Live-Proxies.bat live
```

### Option 4. Run the Python service directly

```bat
venv\Scripts\python Proxy-api.py --api-key MY_API_KEY --tunnel-api-key MY_PROXY_KEY
```

### Option 5. Warmup mode

```bat
venv\Scripts\python Proxy-api.py --warmup --api-key MY_API_KEY --tunnel-api-key MY_PROXY_KEY
```

`--warmup` means the service waits for one full pool build before becoming available.
This is useful when you want the pool ready before your app starts sending traffic.

## Recommended Local Startup

For normal local use:

```bat
venv\Scripts\python Proxy-api.py --warmup --log-requests --api-key MY_API_KEY --tunnel-api-key MY_PROXY_KEY
```

For protected local use:

```bat
venv\Scripts\python Proxy-api.py --warmup --api-key MY_API_KEY --tunnel-api-key MY_PROXY_KEY
```

That gives you:

- API auth through `X-API-Key`
- tunnel auth through standard proxy credentials

## Local URLs You Will Use

### Normal proxy tunnel

```text
http://127.0.0.1:1909
```

### Authenticated proxy tunnel

```text
http://proxy:MY_PROXY_KEY@127.0.0.1:1909
```

`MY_PROXY_KEY` is a password that you choose yourself when starting the service with `--tunnel-api-key`.
It is not auto-generated by the project.

Example:

```bat
venv\Scripts\python Proxy-api.py --tunnel-api-key mysecret123
```

Then the authenticated proxy URL becomes:

```text
http://proxy:mysecret123@127.0.0.1:1909
```

### REST API base

```text
http://127.0.0.1:1712
```

### Raw fetch endpoint

```text
http://127.0.0.1:1712/proxy?url=https://example.com
```

### JSON fetch endpoint

```text
http://127.0.0.1:1712/fetch
```

## Endpoints

### `GET /status`

Shows service health and active pool summary.

Example:

```bat
curl http://127.0.0.1:1712/status
```

You can expect fields like:

- `active_proxies`
- `known_records`
- `best_proxy`
- `sources_count`
- `progress`
- `last_summary`

### `GET /stats`

Shows pool distribution by:

- protocol
- country
- anonymity
- score

### `GET /proxies`

Returns active proxies only.

Common filters:

- `protocol=http`
- `protocol=socks4`
- `protocol=socks5`
- `country=US`
- `anonymity=elite`
- `min_score=0.5`
- `limit=50`

Example:

```bat
curl "http://127.0.0.1:1712/proxies?protocol=http&anonymity=elite&min_score=0.4&limit=20"
```

### `GET /next`

Returns the next active proxy in rotation.

Example:

```bat
curl "http://127.0.0.1:1712/next?protocol=socks5&min_score=0.5"
```

### `GET /random`

Returns a random active proxy from the current live pool.

### `GET` or `POST /proxy`

Fetches the target URL through the proxy pool and returns the raw target response.

This is useful when your app wants the target site's response body directly.

Example:

```bat
curl "http://127.0.0.1:1712/proxy?url=https://httpbin.org/ip"
```

### `GET` or `POST /fetch`

Fetches the target URL through the proxy pool and returns JSON metadata.

This is useful when your app wants:

- which proxy was used
- how many attempts were made
- final URL
- response headers
- response body text

Example:

```bat
curl -X POST http://127.0.0.1:1712/fetch ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://httpbin.org/ip\",\"max_attempts\":10,\"min_score\":0.4}"
```

### `POST /reload`

Forces an immediate refresh cycle.

Example:

```bat
curl -X POST http://127.0.0.1:1712/reload
```

### `GET /tunnel-status`

Shows proxy tunnel usage stats.

## REST API Request Options

For `/fetch` and `/proxy`, common fields are:

- `url`
- `method`
- `headers`
- `body`
- `timeout`
- `max_attempts`
- `expected_status`
- `pool_limit`
- `min_score`
- `allow_redirects`
- `session_id`
- `min_proxy_interval`

Example JSON body:

```json
{
  "url": "https://example.com",
  "method": "GET",
  "headers": {
    "Accept": "text/html"
  },
  "timeout": 20,
  "max_attempts": 10,
  "pool_limit": 50,
  "min_score": 0.4,
  "allow_redirects": true,
  "session_id": "user-1",
  "min_proxy_interval": 0
}
```

## Authentication

### API auth

Start with:

```bat
venv\Scripts\python Proxy-api.py --api-key MY_API_KEY
```

Use with:

```bat
curl -H "X-API-Key: MY_API_KEY" http://127.0.0.1:1712/status
```

### Tunnel auth

Start with:

```bat
venv\Scripts\python Proxy-api.py --tunnel-api-key MY_PROXY_KEY
```

What `MY_PROXY_KEY` means:

- it is the tunnel password you choose yourself
- the project does not generate it automatically
- whatever value you pass to `--tunnel-api-key` becomes the tunnel password
- the default username is `proxy`

Use with:

```text
http://proxy:MY_PROXY_KEY@127.0.0.1:1909
```

Concrete example:

```bat
venv\Scripts\python Proxy-api.py --tunnel-api-key rahul_proxy_2025
```

Then use:

```text
http://proxy:rahul_proxy_2025@127.0.0.1:1909
```

You can also change the tunnel auth username:

```bat
venv\Scripts\python Proxy-api.py --tunnel-api-key MY_PROXY_KEY --tunnel-auth-user rahul
```

Then the proxy URL becomes:

```text
http://rahul:MY_PROXY_KEY@127.0.0.1:1909
```

## Output Files

Each run creates a timestamped folder under `output`.

Typical files:

- `active_proxies.json`
- `session_info.json`

These help you inspect:

- current active pool
- session metadata
- last refresh summary

## How To Use It In Any App

There are two main integration styles.

### Style 1. Use the local tunnel as a normal proxy

This is the easiest option when your language or SDK already supports HTTP proxies.

Your app points to:

```text
http://127.0.0.1:1909
```

or:

```text
http://proxy:MY_PROXY_KEY@127.0.0.1:1909
```

Best for:

- `requests`
- `axios`
- `fetch` wrappers
- Scrapy
- Playwright
- Puppeteer
- Selenium
- browsers
- crawlers
- API clients
- most SDKs with proxy support

### Style 2. Use the local REST API

This is best when your app:

- does not support proxy config directly
- wants metadata about attempts and used proxies
- wants a stable local API contract

Your app calls:

- `http://127.0.0.1:1712/proxy?url=...`
- or `http://127.0.0.1:1712/fetch`

## SDK / Plugin / Integration Explanation

There is no separate custom SDK file in this repo right now.
Instead, this service is intentionally built around universal standards:

- HTTP proxy tunnel
- HTTP REST API

That means almost every language and framework can use it already without needing a special plugin.

If a tool supports:

- HTTP proxy configuration
- SOCKS/HTTP proxy field
- custom base URL
- web requests

then it can integrate with this project.

So in practice, this project already behaves like a provider integration layer.

You can also build your own lightweight SDK wrapper on top of:

- `/fetch`
- `/proxy`
- `/next`
- `/proxies`
- `/stats`

## Language Examples

### Python

Using `requests`:

```python
import requests

proxy_url = "http://127.0.0.1:1909"
proxies = {
    "http": proxy_url,
    "https": proxy_url,
}

r = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=30)
print(r.text)
```

Using REST API:

```python
import requests

r = requests.post(
    "http://127.0.0.1:1712/fetch",
    json={
        "url": "https://httpbin.org/ip",
        "max_attempts": 10,
        "min_score": 0.4
    },
    timeout=60,
)
print(r.json())
```

### JavaScript / Node.js

Using `axios` with the REST API:

```js
const axios = require("axios");

async function main() {
  const res = await axios.post("http://127.0.0.1:1712/fetch", {
    url: "https://httpbin.org/ip",
    max_attempts: 10,
    min_score: 0.4
  });

  console.log(res.data);
}

main();
```

Using a proxy-aware client:

```js
const axios = require("axios");
const HttpsProxyAgent = require("https-proxy-agent");

const proxy = "http://127.0.0.1:1909";
const agent = new HttpsProxyAgent(proxy);

axios.get("https://httpbin.org/ip", {
  httpAgent: agent,
  httpsAgent: agent
}).then(res => {
  console.log(res.data);
});
```

### Browser JavaScript

Direct browser requests usually use the REST API, not the tunnel.

```js
fetch("http://127.0.0.1:1712/fetch", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify({
    url: "https://httpbin.org/ip",
    max_attempts: 10
  })
})
  .then(r => r.json())
  .then(console.log);
```

### Go

Using the tunnel:

```go
package main

import (
	"fmt"
	"io"
	"net/http"
	"net/url"
)

func main() {
	proxyURL, _ := url.Parse("http://127.0.0.1:1909")
	client := &http.Client{
		Transport: &http.Transport{
			Proxy: http.ProxyURL(proxyURL),
		},
	}

	resp, err := client.Get("https://httpbin.org/ip")
	if err != nil {
		panic(err)
	}
	defer resp.Body.Close()

	body, _ := io.ReadAll(resp.Body)
	fmt.Println(string(body))
}
```

### Java

Using the tunnel:

```java
import java.io.InputStream;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.URL;
import java.net.URLConnection;

public class Main {
    public static void main(String[] args) throws Exception {
        Proxy proxy = new Proxy(Proxy.Type.HTTP, new InetSocketAddress("127.0.0.1", 1909));
        URLConnection conn = new URL("https://httpbin.org/ip").openConnection(proxy);
        InputStream in = conn.getInputStream();
        System.out.println(new String(in.readAllBytes()));
    }
}
```

### C#

Using the tunnel:

```csharp
using System;
using System.Net;
using System.Net.Http;
using System.Threading.Tasks;

class Program
{
    static async Task Main()
    {
        var handler = new HttpClientHandler
        {
            Proxy = new WebProxy("http://127.0.0.1:1909"),
            UseProxy = true
        };

        using var client = new HttpClient(handler);
        var body = await client.GetStringAsync("https://httpbin.org/ip");
        Console.WriteLine(body);
    }
}
```

### PHP

Using the tunnel:

```php
<?php
$ch = curl_init("https://httpbin.org/ip");
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_PROXY, "http://127.0.0.1:1909");
$response = curl_exec($ch);
curl_close($ch);
echo $response;
```

### Ruby

Using the tunnel:

```ruby
require "net/http"
require "uri"

proxy = URI("http://127.0.0.1:1909")
target = URI("https://httpbin.org/ip")

http = Net::HTTP::Proxy(proxy.host, proxy.port).new(target.host, target.port)
http.use_ssl = true

request = Net::HTTP::Get.new(target)
response = http.request(request)
puts response.body
```

### Rust

Using the tunnel with `reqwest`:

```rust
use reqwest::Proxy;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proxy = Proxy::all("http://127.0.0.1:1909")?;
    let client = reqwest::Client::builder().proxy(proxy).build()?;
    let body = client.get("https://httpbin.org/ip").send().await?.text().await?;
    println!("{}", body);
    Ok(())
}
```

### cURL

Using the tunnel:

```bat
curl -x http://127.0.0.1:1909 https://httpbin.org/ip
```

Using the authenticated tunnel:

```bat
curl -x http://proxy:MY_PROXY_KEY@127.0.0.1:1909 https://httpbin.org/ip
```

Using the REST API:

```bat
curl "http://127.0.0.1:1712/proxy?url=https://httpbin.org/ip"
```

## Common App Integrations

### Scrapy

```python
HTTP_PROXY = "http://127.0.0.1:1909"
HTTPS_PROXY = "http://127.0.0.1:1909"
```

### Playwright

```python
browser = playwright.chromium.launch(
    proxy={"server": "http://127.0.0.1:1909"}
)
```

### Puppeteer

Launch Chromium with:

```text
--proxy-server=http://127.0.0.1:1909
```

### Selenium

Configure browser proxy settings to:

```text
127.0.0.1:1909
```

### Postman

Use the local REST API:

- `POST http://127.0.0.1:1712/fetch`

or set Postman's global proxy to:

- host `127.0.0.1`
- port `1909`

### Electron apps

You can either:

- use the REST API
- or configure Chromium proxy settings to `http://127.0.0.1:1909`

### Any SDK or plugin that supports proxies

Look for settings such as:

- proxy URL
- HTTP proxy
- HTTPS proxy
- outbound proxy
- transport proxy
- network proxy

and set it to:

```text
http://127.0.0.1:1909
```

## Optional Browser Stealth Helper

The main project is the proxy service.
Browser stealth is optional.

If you need browser-level help, `stealth_browser.py` can try:

1. CloakBrowser
2. Camoufox
3. Playwright

Run:

```bat
venv\Scripts\python stealth_browser.py https://httpbin.org/ip --engine auto
```

Library example:

```python
import asyncio
from stealth_browser import scrape_url

result = asyncio.run(scrape_url("https://httpbin.org/ip"))
print(result["status"])
print(result["content_length"])
```

Important boundary:

- proxy tunnel handles proxy rotation and failover
- browser helper handles browser-level fingerprint surfaces

The tunnel itself cannot rewrite Canvas, WebGL, Audio, fonts, or JavaScript APIs inside encrypted HTTPS pages.

## CLI Reference

Most important flags for [Proxy-api.py](</c:/Users/Admin/Desktop/Proxy Generator/Proxy-api.py>):

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | API bind host |
| `--port` | `1712` | API bind port |
| `--public-base-url` | empty | public URL label if exposed elsewhere |
| `--output-root` | `output` | run output folder root |
| `--session-prefix` | `api` | run folder prefix |
| `--max-concurrent` | `120` | source fetch and validation concurrency |
| `--fetch-timeout` | `8.0` | source download timeout |
| `--verify-timeout` | `8.0` | proxy validation timeout |
| `--request-timeout` | `20.0` | target request timeout |
| `--request-concurrency` | `200` | outbound target request concurrency |
| `--refresh-delay` | `5.0` | refresh loop delay |
| `--update-interval` | `120.0` | source refresh interval |
| `--verify-interval` | `60.0` | active pool re-check interval |
| `--auto-save-interval` | `15.0` | minimum JSON save interval |
| `--max-candidates` | `1000` | max candidates per cycle |
| `--verify-batch-size` | `120` | active proxy verify batch size |
| `--min-success-rate` | `0.35` | minimum acceptable success rate |
| `--max-failures` | `3` | max consecutive failures |
| `--stale-after` | `1800` | stale proxy lifetime in seconds |
| `--max-response-time` | `12.0` | max average proxy response time |
| `--source-file` | empty | custom extra source list |
| `--warmup` | off | build pool before accepting traffic |
| `--proxy-delay` | `0.1` | delay between proxy attempts |
| `--rotate-ua` | on | rotate HTTP headers and user-agent |
| `--no-shuffle-proxies` | off | preserve rank order instead of shuffling |
| `--api-key` | required | REST API auth key |
| `--cors-origin` | `*` | CORS allow origin |
| `--max-response-mb` | `10.0` | max response size |
| `--log-requests` | off | request logging |
| `--tunnel-host` | `127.0.0.1` | tunnel bind host |
| `--tunnel-port` | `1909` | tunnel port |
| `--tunnel-max-attempts` | `5` | attempts per tunnel request |
| `--tunnel-relay-timeout` | `120.0` | tunnel idle timeout |
| `--tunnel-api-key` | required when tunnel is enabled | standard proxy auth password |
| `--tunnel-auth-user` | `proxy` | standard proxy auth username |

## Startup Checklist

When using this in a real app, the practical setup order is:

1. install dependencies
2. run `Start-Live-Proxies.bat` or start `Proxy-api.py`
3. wait until `/status` shows active proxies
4. test with `http://127.0.0.1:1712/status`
5. test tunnel with `curl -x http://127.0.0.1:1909 https://httpbin.org/ip`
6. point your real project to the local tunnel or local REST API

## Testing Commands

### Syntax check

```bat
venv\Scripts\python -m py_compile proxy_core.py Proxy-api.py stealth_browser.py
```

### Status check

```bat
curl http://127.0.0.1:1712/status
```

### Rotation check

```bat
for /L %i in (1,1,5) do curl "http://127.0.0.1:1712/proxy?url=http://api.ipify.org%%3Fformat%%3Djson"
```

### Auth check

```bat
curl -H "X-API-Key: MY_API_KEY" http://127.0.0.1:1712/status
curl -x http://proxy:MY_PROXY_KEY@127.0.0.1:1909 https://httpbin.org/ip
```

## Best Practices

- keep the service local unless you really need LAN exposure
- use `--api-key` and `--tunnel-api-key` if exposing it beyond your machine
- prefer `--warmup` before connecting your app
- use `max_attempts >= 10` for unstable targets
- use `min_score >= 0.4` when you want more stable proxies
- use `session_id` when the same logical user flow needs the same proxy
- monitor `/status` and `/stats` if your app depends on sustained throughput

## Limits

This service does a lot for free proxies, but some limits are real:

- free proxies are not as reliable as premium providers
- target websites may still block some datacenter IPs
- browser fingerprint handling is not the same thing as proxy rotation
- some apps only support HTTP proxy config and not custom API flows

Still, for local use, development, research, scraping experiments, proxy rotation workflows, and universal proxy integration, this project is designed to be a strong one-stop setup.

## Credits and Acknowledgements

This project stands on top of a number of useful open-source libraries, tools, and public proxy-list projects.
Credit is due to the maintainers and contributors behind them.

### Core libraries used by this project

- `aiohttp` for the async HTTP client and server foundation
- `aiohttp-socks` for SOCKS proxy support
- `python-socks` for low-level SOCKS tunnel connectivity
- `requests` for simple HTTP integration examples
- `rich` for the live terminal UI and readable console output

### Optional browser helper ecosystem

- `CloakBrowser` for browser-level stealth and fingerprint resistance
- `Camoufox` for Firefox-based anti-detection support
- `Playwright` for browser automation fallback support

### Public proxy source ecosystem

This project also depends on public proxy-list providers and repositories that publish free proxy data.
Examples include:

- `proxifly/free-proxy-list`
- `TheSpeedX/PROXY-List`
- `monosans/proxy-list`
- `vakhov/fresh-proxy-list`
- `MuRongPIG/Proxy-Master`
- `Zaeem20/FREE_PROXIES_LIST`
- `rdavydov/proxy-list`
- `ProxyScrape`
- `Geonode`
- `proxy-list.download`
- `openproxylist`

The active runtime source list is maintained directly in [proxy_core.py](</c:/Users/Admin/Desktop/Proxy Generator/proxy_core.py:39>) under `DEFAULT_SOURCES`.

### Note on ownership

This project integrates with and builds on top of external libraries and public data sources, but it is not affiliated with, endorsed by, or officially maintained by those third-party projects.

## Final Mental Model

If your app supports a proxy field, use:

```text
http://127.0.0.1:1909
```

If your app supports only HTTP API calls, use:

```text
http://127.0.0.1:1712/fetch
```

If your app wants raw target content through the pool, use:

```text
http://127.0.0.1:1712/proxy?url=YOUR_TARGET_URL
```

That is the whole product shape.
Run it once, then treat it like your own local proxy provider.
