#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Any,
    Callable,
    DefaultDict,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
)

import aiohttp

try:
    import aiohttp_socks
    _SOCKS_OK = True
except ImportError:
    _SOCKS_OK = False

DEFAULT_OUTPUT_FILE = "active_proxies.json"
DEFAULT_USER_AGENT = "ProxyGenerator/2.0 (+local pool manager)"
DEFAULT_TEST_URLS = (
    "http://httpbin.org/ip",
    "http://api.ipify.org?format=json",
)
DEFAULT_SOURCES = (
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/theriturajps/proxy-list/main/proxies.txt",
    "https://raw.githubusercontent.com/komutan234/Proxy-List-Free/main/proxies/http.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/http.txt",
    "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/http.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt",
    "https://raw.githubusercontent.com/gitrecon1455/fresh-proxy-list/main/all.txt",
    "https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/https.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    "https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://api.openproxylist.xyz/http.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list/data.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt",
    "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/prxchk/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/master/http.txt",
    # --- Additional HTTP sources ---
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
    "https://raw.githubusercontent.com/elliottophellia/yakumo/master/results/http/global/http_checked.txt",
    "https://raw.githubusercontent.com/Anonym0usWork1221/Free-Proxies/main/proxy_files/http_proxies.txt",
    "https://raw.githubusercontent.com/casals-ar/proxy-list/main/http",
    "https://raw.githubusercontent.com/rxvl-d/ProxyList/main/results.txt",
    "https://raw.githubusercontent.com/UptimerBot/proxy-list/main/proxies/http.txt",
    # --- Fresh/high-update sources (every 5-30 min) ---
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt",
    "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/http.txt",
    "https://raw.githubusercontent.com/rx443/proxy-list/online/online/http.txt",
    "https://raw.githubusercontent.com/TuanMinPay/live-proxy/master/http.txt",
    "https://raw.githubusercontent.com/HyperBeats/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/http.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/https.txt",
    "https://raw.githubusercontent.com/ProxyScraper/ProxyScraper/main/http.txt",
    "https://raw.githubusercontent.com/proxylist-to/proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies_anonymous/http.txt",
    "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/http.txt",
    "https://raw.githubusercontent.com/hanwayTech/free-proxy-list/main/http.txt",
    "https://raw.githubusercontent.com/hanwayTech/free-proxy-list/main/https.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies_anonymous/http.txt",
    "https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/https.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/https.txt",
    # --- ProxyScrape API (multiple protocols) ---
    "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=http&timeout=10000&country=all&anonymity=all",
    "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks5&timeout=10000",
    "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&protocol=socks4&timeout=10000",
    # --- SOCKS5 sources ---
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
    "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/ObcbO/getproxy/master/file/socks5.txt",
    # --- SOCKS4 sources ---
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks4.txt",
    "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt",
    "https://raw.githubusercontent.com/MuRongPIG/Proxy-Master/main/socks4.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks4.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks4.txt",
    # --- APIs that return JSON (regex still extracts IP:port) ---
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&filterUpTime=90&protocols=http",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&filterUpTime=90&protocols=socks5",
)

PROXY_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b")
PROXY_WITH_AUTH_PATTERN = re.compile(
    r"(?:http|socks4|socks5)://[\w\-]+:[\w\-]+@(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}"
)

# Enrichment endpoints
ANONYMITY_CHECK_URL = "http://httpbin.org/headers"
GEO_API_URL = "http://ip-api.com/json/{ip}?fields=status,countryCode"
_GEO_ENRICH_CONCURRENCY = 5  # ip-api.com free tier: 45 req/min
_ANONYMITY_ENRICH_CONCURRENCY = 15
_ENRICH_BATCH_SIZE = 25


def normalize_proxy(candidate: str) -> Optional[str]:
    value = candidate.strip()
    if not value:
        return None

    protocol = "http"
    if "://" in value:
        parts = value.split("://", 1)
        protocol = parts[0].lower()
        if protocol not in ("http", "https", "socks4", "socks5"):
            protocol = "http"
            value = parts[1]
        else:
            value = parts[1]

    if "@" in value:
        value = value.split("@", 1)[1]

    if ":" not in value:
        return None

    host, port_text = value.rsplit(":", 1)
    octets = host.split(".")
    if len(octets) != 4:
        return None

    try:
        if any(int(part) < 0 or int(part) > 255 for part in octets):
            return None
        port = int(port_text)
    except ValueError:
        return None

    if not 1 <= port <= 65535:
        return None

    return f"{protocol}://{host}:{port}"


def _ignore_known_windows_asyncio_noise(
    loop: asyncio.AbstractEventLoop, context: Dict[str, Any]
) -> None:
    if sys.platform != "win32":
        loop.default_exception_handler(context)
        return

    exc = context.get("exception")
    handle_text = repr(context.get("handle", ""))
    message = str(context.get("message", ""))

    if isinstance(exc, ConnectionResetError) and (
        "_ProactorBasePipeTransport._call_connection_lost" in handle_text
        or "_ProactorBasePipeTransport" in message
    ):
        return

    loop.default_exception_handler(context)


def run_async_entrypoint(coro):
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None
    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.get_loop().set_exception_handler(_ignore_known_windows_asyncio_noise)
        return runner.run(coro)


def run_async_with_cleanup(coro, cleanup_callback=None):
    loop_factory = asyncio.SelectorEventLoop if sys.platform == "win32" else None

    async def run_with_signal_handling():
        interrupt_event = asyncio.Event()
        loop = asyncio.get_running_loop()

        def signal_handler():
            print("\nShutdown signal received, cleaning up...")
            interrupt_event.set()

        if sys.platform != "win32":
            for sig in (asyncio.signals.SIGINT, asyncio.signals.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)

        async def run_coro():
            try:
                await coro
            finally:
                if cleanup_callback:
                    await cleanup_callback()

        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(run_coro())
                tg.create_task(interrupt_event.wait())
        except (asyncio.CancelledError, KeyboardInterrupt):
            pass

    with asyncio.Runner(loop_factory=loop_factory) as runner:
        runner.get_loop().set_exception_handler(_ignore_known_windows_asyncio_noise)
        return runner.run(run_with_signal_handling())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return utc_now()
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def extract_proxies(text: str) -> Set[str]:
    proxies: Set[str] = set()

    for raw_proxy in PROXY_WITH_AUTH_PATTERN.findall(text):
        normalized = normalize_proxy(raw_proxy)
        if normalized:
            proxies.add(normalized)

    for raw_proxy in PROXY_PATTERN.findall(text):
        normalized = normalize_proxy(raw_proxy)
        if normalized:
            proxies.add(normalized)

    return proxies


def read_source_file(path: str | None) -> List[str]:
    if not path:
        return []
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"source file not found: {file_path}")
    urls = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        cleaned = line.strip()
        if cleaned and not cleaned.startswith("#"):
            urls.append(cleaned)
    return urls


def _extract_origin(body: str) -> str:
    stripped = body.strip()
    if not stripped:
        return ""
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            for key in ("origin", "ip", "query"):
                value = payload.get(key)
                if value:
                    return str(value)
    except json.JSONDecodeError:
        pass

    ip_match = re.search(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", stripped)
    if ip_match:
        return ip_match.group(0)
    return ""


def _extract_ip(proxy_url: str) -> str:
    """Extract bare IP from a proxy URL like http://1.2.3.4:8080."""
    try:
        clean = proxy_url.split("://", 1)[-1].split("@")[-1]
        return clean.split(":")[0]
    except Exception:
        return ""


async def _check_anonymity_via_socks(proxy_url: str, timeout_seconds: float) -> str:
    if not _SOCKS_OK:
        return ""
    try:
        connector = aiohttp_socks.ProxyConnector.from_url(proxy_url, ssl=False)
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as s:
            async with s.get(
                ANONYMITY_CHECK_URL,
                timeout=timeout,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as response:
                if response.status != 200:
                    return ""
                data = await response.json(content_type=None)
                received = {k.lower(): v for k, v in data.get("headers", {}).items()}
                if "x-forwarded-for" in received or "x-real-ip" in received:
                    return "transparent"
                if "via" in received or "proxy-connection" in received:
                    return "anonymous"
                return "elite"
    except Exception:
        return ""


async def check_proxy_anonymity(
    session: aiohttp.ClientSession,
    proxy_url: str,
    timeout_seconds: float = 8.0,
) -> str:
    """Return 'elite', 'anonymous', 'transparent', or '' on failure."""
    if proxy_url.startswith("socks"):
        return await _check_anonymity_via_socks(proxy_url, timeout_seconds)
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with session.get(
            ANONYMITY_CHECK_URL,
            proxy=proxy_url,
            timeout=timeout,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as response:
            if response.status != 200:
                return ""
            data = await response.json(content_type=None)
            received = {k.lower(): v for k, v in data.get("headers", {}).items()}
            if "x-forwarded-for" in received or "x-real-ip" in received:
                return "transparent"
            if "via" in received or "proxy-connection" in received:
                return "anonymous"
            return "elite"
    except Exception:
        return ""


async def lookup_proxy_country(
    session: aiohttp.ClientSession,
    ip: str,
    timeout_seconds: float = 5.0,
) -> str:
    """Return ISO-2 country code for *ip* using ip-api.com, or '' on failure."""
    if not ip:
        return ""
    try:
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with session.get(
            GEO_API_URL.format(ip=ip),
            timeout=timeout,
        ) as response:
            if response.status != 200:
                return ""
            data = await response.json(content_type=None)
            if data.get("status") == "success":
                return str(data.get("countryCode", ""))
    except Exception:
        return ""
    return ""


@dataclass
class HarvesterConfig:
    max_concurrent: int = 200
    fetch_timeout: float = 10.0
    verify_timeout: float = 10.0
    update_interval: float = 120.0
    verify_interval: float = 60.0
    auto_save_interval: float = 15.0
    max_candidates: int = 3000
    verify_batch_size: int = 200
    min_success_rate: float = 0.35
    max_consecutive_failures: int = 3
    max_stored_records: int = 5000
    stale_after_seconds: float = 1800.0
    max_response_time: float = 12.0
    output_file: str = DEFAULT_OUTPUT_FILE
    user_agent: str = DEFAULT_USER_AGENT
    test_urls: List[str] = field(default_factory=lambda: list(DEFAULT_TEST_URLS))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_concurrent": self.max_concurrent,
            "fetch_timeout": self.fetch_timeout,
            "verify_timeout": self.verify_timeout,
            "update_interval": self.update_interval,
            "verify_interval": self.verify_interval,
            "auto_save_interval": self.auto_save_interval,
            "max_candidates": self.max_candidates,
            "verify_batch_size": self.verify_batch_size,
            "min_success_rate": self.min_success_rate,
            "max_consecutive_failures": self.max_consecutive_failures,
            "stale_after_seconds": self.stale_after_seconds,
            "max_response_time": self.max_response_time,
            "output_file": self.output_file,
            "user_agent": self.user_agent,
            "test_urls": list(self.test_urls),
        }


@dataclass
class ProxyRecord:
    proxy: str
    first_seen: datetime = field(default_factory=utc_now)
    last_seen_success: datetime = field(default_factory=utc_now)
    last_checked: datetime = field(default_factory=utc_now)
    total_checks: int = 0
    successful_checks: int = 0
    consecutive_failures: int = 0
    response_times: List[float] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)
    last_error: str = ""
    last_probe_url: str = ""
    last_origin: str = ""
    anonymity: str = ""   # "elite" | "anonymous" | "transparent" | ""
    country: str = ""     # ISO-2 country code or ""
    success_rate: float = 0.0
    avg_response_time: float = 0.0
    score: float = 0.0
    _last_used_at: float = field(default=0.0, init=False, compare=False, repr=False)

    @property
    def protocol(self) -> str:
        if "://" in self.proxy:
            return self.proxy.split("://", 1)[0].lower()
        return "http"

    def mark_used(self) -> None:
        self._last_used_at = time.monotonic()

    def on_cooldown(self, min_interval_seconds: float = 0.0) -> bool:
        if min_interval_seconds <= 0:
            return False
        return (time.monotonic() - self._last_used_at) < min_interval_seconds

    def add_sources(self, urls: Iterable[str]) -> None:
        merged = set(self.source_urls)
        merged.update(urls)
        self.source_urls = sorted(merged)[:10]

    def record_success(
        self,
        response_time: float,
        probe_url: str,
        origin: str,
        max_response_time: float,
    ) -> None:
        self.total_checks += 1
        self.successful_checks += 1
        self.consecutive_failures = 0
        self.last_checked = utc_now()
        self.last_seen_success = self.last_checked
        self.last_error = ""
        self.last_probe_url = probe_url
        self.last_origin = origin
        self.response_times.append(round(response_time, 4))
        if len(self.response_times) > 20:
            self.response_times = self.response_times[-20:]
        self.recalculate(max_response_time)

    def record_failure(
        self, error: str, probe_url: str, max_response_time: float
    ) -> None:
        self.total_checks += 1
        self.consecutive_failures += 1
        self.last_checked = utc_now()
        self.last_error = error
        self.last_probe_url = probe_url
        self.recalculate(max_response_time)

    def recalculate(
        self, max_response_time: float, freshness_window_seconds: float = 3600.0
    ) -> None:
        self.success_rate = (
            (self.successful_checks / self.total_checks) if self.total_checks else 0.0
        )
        self.avg_response_time = (
            sum(self.response_times) / len(self.response_times)
            if self.response_times
            else 0.0
        )
        freshness = (
            0.0
            if self.successful_checks == 0
            else max(
                0.0,
                1.0
                - min(
                    (utc_now() - self.last_seen_success).total_seconds(),
                    freshness_window_seconds,
                )
                / freshness_window_seconds,
            )
        )
        speed = (
            0.0
            if self.avg_response_time <= 0
            else max(
                0.0,
                1.0
                - min(self.avg_response_time, max_response_time) / max_response_time,
            )
        )
        stability = max(0.0, 1.0 - min(self.consecutive_failures, 5) / 5.0)
        self.score = round(
            (self.success_rate * 0.50)
            + (speed * 0.25)
            + (freshness * 0.15)
            + (stability * 0.10),
            6,
        )

    def is_active(self, config: HarvesterConfig) -> bool:
        if self.successful_checks == 0:
            return False
        if self.consecutive_failures >= config.max_consecutive_failures:
            return False
        if self.total_checks >= 3 and self.success_rate < config.min_success_rate:
            return False
        if self.avg_response_time and self.avg_response_time > config.max_response_time:
            return False
        return (
            utc_now() - self.last_seen_success
        ).total_seconds() <= config.stale_after_seconds

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proxy": self.proxy,
            "protocol": self.protocol,
            "first_seen": to_iso(self.first_seen),
            "last_seen_success": to_iso(self.last_seen_success),
            "last_seen": to_iso(self.last_seen_success),
            "last_checked": to_iso(self.last_checked),
            "total_checks": self.total_checks,
            "successful_checks": self.successful_checks,
            "consecutive_failures": self.consecutive_failures,
            "response_times": self.response_times,
            "source_urls": self.source_urls,
            "last_error": self.last_error,
            "last_probe_url": self.last_probe_url,
            "last_origin": self.last_origin,
            "anonymity": self.anonymity,
            "country": self.country,
            "success_rate": round(self.success_rate, 6),
            "avg_response_time": round(self.avg_response_time, 4),
            "score": round(self.score, 6),
        }

    @classmethod
    def from_dict(
        cls, payload: Dict[str, Any], max_response_time: float = 12.0
    ) -> "ProxyRecord":
        record = cls(
            proxy=payload["proxy"],
            first_seen=parse_datetime(
                payload.get("first_seen") or payload.get("last_seen")
            ),
            last_seen_success=parse_datetime(
                payload.get("last_seen_success") or payload.get("last_seen")
            ),
            last_checked=parse_datetime(
                payload.get("last_checked") or payload.get("last_seen")
            ),
            total_checks=int(payload.get("total_checks", 0)),
            successful_checks=int(payload.get("successful_checks", 0)),
            consecutive_failures=int(payload.get("consecutive_failures", 0)),
            response_times=[
                float(value) for value in payload.get("response_times", [])
            ],
            source_urls=list(payload.get("source_urls", [])),
            last_error=str(payload.get("last_error", "")),
            last_probe_url=str(payload.get("last_probe_url", "")),
            last_origin=str(payload.get("last_origin", "")),
            anonymity=str(payload.get("anonymity", "")),
            country=str(payload.get("country", "")),
            success_rate=float(payload.get("success_rate", 0.0)),
            avg_response_time=float(payload.get("avg_response_time", 0.0)),
            score=float(payload.get("score", 0.0)),
        )
        record.recalculate(max_response_time)
        return record


def load_proxy_records(
    path: str | Path, max_response_time: float = 12.0
) -> Dict[str, ProxyRecord]:
    file_path = Path(path)
    if not file_path.exists():
        return {}
    raw = json.loads(file_path.read_text(encoding="utf-8"))
    items = raw.get("proxies", []) if isinstance(raw, dict) else raw
    records: Dict[str, ProxyRecord] = {}
    for item in items:
        try:
            record = ProxyRecord.from_dict(item, max_response_time)
            records[record.proxy] = record
        except Exception:
            continue
    return records


def load_ranked_records(
    path: str | Path,
    limit: int | None = None,
    min_score: float = 0.0,
    max_response_time: float = 12.0,
) -> List[ProxyRecord]:
    records = [
        record
        for record in load_proxy_records(path, max_response_time).values()
        if record.score >= min_score
    ]
    records.sort(
        key=lambda item: (
            -item.score,
            -item.success_rate,
            item.avg_response_time or 9999.0,
            item.proxy,
        )
    )
    return records if limit is None else records[:limit]


@dataclass
class ProbeOutcome:
    proxy: str
    working: bool
    response_time: float = 0.0
    probe_url: str = ""
    error: str = ""
    origin: str = ""
    status_code: int = 0


async def _probe_socks_proxy(
    proxy: str,
    proxy_url: str,
    test_urls: Sequence[str],
    timeout_seconds: float,
    user_agent: str,
) -> ProbeOutcome:
    if not _SOCKS_OK:
        return ProbeOutcome(proxy=proxy, working=False, error="aiohttp_socks not installed")
    headers = {"User-Agent": user_agent, "Accept": "application/json,text/plain,*/*"}
    errors: List[str] = []
    try:
        connector = aiohttp_socks.ProxyConnector.from_url(proxy_url, ssl=False)
        async with aiohttp.ClientSession(connector=connector, trust_env=False) as socks_session:
            for test_url in test_urls:
                started = time.perf_counter()
                try:
                    timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                    async with socks_session.get(
                        test_url, headers=headers, timeout=timeout, allow_redirects=True,
                    ) as response:
                        body = await response.text()
                        if response.status != 200:
                            errors.append(f"{response.status} from {test_url}")
                            continue
                        origin = _extract_origin(body)
                        if not origin:
                            errors.append(f"no origin from {test_url}")
                            continue
                        return ProbeOutcome(
                            proxy=proxy, working=True,
                            response_time=time.perf_counter() - started,
                            probe_url=test_url, origin=origin, status_code=response.status,
                        )
                except asyncio.TimeoutError:
                    errors.append(f"timeout from {test_url}")
                except Exception as exc:
                    errors.append(f"{exc.__class__.__name__} from {test_url}")
    except Exception as exc:
        errors.append(f"connector: {exc.__class__.__name__}")
    return ProbeOutcome(
        proxy=proxy, working=False,
        error="; ".join(errors[:3]) if errors else "unknown error",
    )


async def probe_proxy(
    session: aiohttp.ClientSession,
    proxy: str,
    test_urls: Sequence[str],
    timeout_seconds: float,
    user_agent: str = DEFAULT_USER_AGENT,
) -> ProbeOutcome:
    headers = {"User-Agent": user_agent, "Accept": "application/json,text/plain,*/*"}
    proxy_url = proxy if "://" in proxy else f"http://{proxy}"
    errors: List[str] = []

    if proxy_url.startswith(("socks4://", "socks5://")):
        return await _probe_socks_proxy(proxy, proxy_url, test_urls, timeout_seconds, user_agent)

    for test_url in test_urls:
        started = time.perf_counter()
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_seconds)
            async with session.get(
                test_url,
                headers=headers,
                proxy=proxy_url,
                timeout=timeout,
                allow_redirects=True,
            ) as response:
                body = await response.text()
                if response.status != 200:
                    errors.append(f"{response.status} from {test_url}")
                    continue
                origin = _extract_origin(body)
                if not origin:
                    errors.append(f"unexpected response from {test_url}")
                    continue
                return ProbeOutcome(
                    proxy=proxy,
                    working=True,
                    response_time=time.perf_counter() - started,
                    probe_url=test_url,
                    origin=origin,
                    status_code=response.status,
                )
        except asyncio.TimeoutError:
            errors.append(f"timeout from {test_url}")
        except aiohttp.ClientError as exc:
            errors.append(f"{exc.__class__.__name__} from {test_url}")
        except Exception as exc:
            errors.append(f"{exc.__class__.__name__} from {test_url}")

    return ProbeOutcome(
        proxy=proxy,
        working=False,
        error="; ".join(errors[:3]) if errors else "unknown error",
    )


class ProxyHarvester:
    def __init__(
        self,
        config: HarvesterConfig,
        sources: Optional[Sequence[str]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.config = config
        self.sources = list(sources or DEFAULT_SOURCES)
        self.progress_callback = progress_callback
        self.records: Dict[str, ProxyRecord] = {}
        self.active_proxies: Set[str] = set()
        self.source_counts: Dict[str, int] = {}
        self.source_errors: Dict[str, str] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_collect = 0.0
        self._last_verify = 0.0
        self._last_save = 0.0
        self._round_robin_index: int = 0

    def _emit_progress(self, **payload: Any) -> None:
        if not self.progress_callback:
            return
        self.progress_callback(payload)

    async def __aenter__(self) -> "ProxyHarvester":
        connector = aiohttp.TCPConnector(limit=self.config.max_concurrent, ssl=True)
        self.session = aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": self.config.user_agent},
            trust_env=False,
        )
        self.records = load_proxy_records(
            self.config.output_file, self.config.max_response_time
        )
        self._rebuild_active_proxies()
        self._last_collect = time.monotonic() - self.config.update_interval
        self._last_verify = time.monotonic() - self.config.verify_interval
        self._last_save = 0.0
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.session:
            await self.session.close()

    def _rebuild_active_proxies(self) -> None:
        self.active_proxies = {
            proxy
            for proxy, record in self.records.items()
            if record.is_active(self.config)
        }

    def ranked_active_records(self, limit: int | None = None) -> List[ProxyRecord]:
        records = [
            self.records[proxy]
            for proxy in self.active_proxies
            if proxy in self.records
        ]
        records.sort(
            key=lambda item: (
                -item.score,
                -item.success_rate,
                item.avg_response_time or 9999.0,
                item.proxy,
            )
        )
        return records if limit is None else records[:limit]

    def best_proxy(self) -> Optional[ProxyRecord]:
        ranked = self.ranked_active_records(limit=1)
        return ranked[0] if ranked else None

    def _filtered_records(
        self,
        protocol: Optional[str] = None,
        country: Optional[str] = None,
        anonymity: Optional[str] = None,
        min_score: float = 0.0,
        limit: Optional[int] = None,
    ) -> List[ProxyRecord]:
        """Return ranked active records matching all non-None filter criteria."""
        records = self.ranked_active_records()
        if min_score > 0:
            records = [r for r in records if r.score >= min_score]
        if protocol:
            records = [r for r in records if r.protocol == protocol.lower()]
        if country:
            records = [r for r in records if r.country.upper() == country.upper()]
        if anonymity:
            records = [r for r in records if r.anonymity == anonymity.lower()]
        return records if limit is None else records[:limit]

    def next_proxy(
        self,
        protocol: Optional[str] = None,
        country: Optional[str] = None,
        anonymity: Optional[str] = None,
        min_score: float = 0.0,
        skip_cooldown: float = 0.0,
    ) -> Optional[ProxyRecord]:
        """Round-robin: return next proxy matching criteria and advance the index."""
        records = self._filtered_records(
            protocol=protocol, country=country, anonymity=anonymity, min_score=min_score
        )
        if skip_cooldown > 0:
            records = [r for r in records if not r.on_cooldown(skip_cooldown)]
        if not records:
            return None
        if self._round_robin_index >= len(records):
            self._round_robin_index = 0
        record = records[self._round_robin_index]
        self._round_robin_index = (self._round_robin_index + 1) % len(records)
        return record

    async def _enrich_pool(self) -> None:
        """Detect anonymity level and country for active proxies that lack this data."""
        if not self.session:
            return
        candidates = [
            record
            for proxy, record in self.records.items()
            if proxy in self.active_proxies
            and (not record.anonymity or not record.country)
        ]
        if not candidates:
            return
        candidates = candidates[:_ENRICH_BATCH_SIZE]

        sem_anon = asyncio.Semaphore(_ANONYMITY_ENRICH_CONCURRENCY)
        sem_geo = asyncio.Semaphore(_GEO_ENRICH_CONCURRENCY)

        async def enrich(record: ProxyRecord) -> None:
            proxy_url = record.proxy if "://" in record.proxy else f"http://{record.proxy}"
            try:
                if not record.anonymity:
                    async with sem_anon:
                        anon = await check_proxy_anonymity(
                            self.session,  # type: ignore[arg-type]
                            proxy_url,
                            self.config.verify_timeout,
                        )
                        if anon:
                            record.anonymity = anon
                if not record.country:
                    ip = _extract_ip(proxy_url)
                    async with sem_geo:
                        # Small delay to stay within ip-api.com free rate limit (45/min)
                        await asyncio.sleep(0.15)
                        country = await lookup_proxy_country(
                            self.session,  # type: ignore[arg-type]
                            ip,
                            5.0,
                        )
                        if country:
                            record.country = country
            except Exception:
                pass

        await asyncio.gather(*(enrich(record) for record in candidates))

    def save_pool(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - self._last_save) < self.config.auto_save_interval:
            return

        payload = {
            "updated_at": to_iso(utc_now()),
            "count": len(self.active_proxies),
            "summary": {
                "known_records": len(self.records),
                "active_records": len(self.active_proxies),
                "sources": len(self.sources),
            },
            "config": self.config.to_dict(),
            "sources": [
                {
                    "url": url,
                    "last_count": self.source_counts.get(url, 0),
                    "last_error": self.source_errors.get(url, ""),
                }
                for url in self.sources
            ],
            "proxies": [record.to_dict() for record in self.ranked_active_records()],
        }
        Path(self.config.output_file).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
        self._last_save = now

    async def _fetch_source(self, url: str, retries: int = 2) -> Set[str]:
        if not self.session:
            raise RuntimeError("harvester session is not ready")

        last_error = ""
        for attempt in range(retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.config.fetch_timeout)
                async with self.session.get(
                    url, timeout=timeout, allow_redirects=True
                ) as response:
                    if response.status == 429:
                        self.source_counts[url] = 0
                        self.source_errors[url] = "rate_limited"
                        return set()
                    if response.status != 200:
                        last_error = f"http {response.status}"
                        if attempt < retries:
                            await asyncio.sleep(1.0 * (attempt + 1))
                            continue
                        self.source_counts[url] = 0
                        self.source_errors[url] = last_error
                        return set()
                    proxies = extract_proxies(await response.text())
                    self.source_counts[url] = len(proxies)
                    self.source_errors[url] = ""
                    return proxies
            except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
                last_error = exc.__class__.__name__
                if attempt < retries:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as exc:
                self.source_counts[url] = 0
                self.source_errors[url] = exc.__class__.__name__
                return set()

        self.source_counts[url] = 0
        self.source_errors[url] = last_error
        return set()

    async def collect_candidates(self) -> Dict[str, Set[str]]:
        candidate_sources: DefaultDict[str, Set[str]] = defaultdict(set)
        total_sources = len(self.sources)
        completed_sources = 0

        self._emit_progress(
            phase="collecting_sources",
            total_sources=total_sources,
            completed_sources=0,
            collected_candidates=0,
        )

        async def worker(url: str) -> None:
            nonlocal completed_sources
            try:
                result = await self._fetch_source(url)
            except Exception as exc:
                self.source_counts[url] = 0
                self.source_errors[url] = exc.__class__.__name__
                result = set()

            for proxy in result:
                candidate_sources[proxy].add(url)

            completed_sources += 1
            self._emit_progress(
                phase="collecting_sources",
                current_source=url,
                current_source_count=len(result),
                total_sources=total_sources,
                completed_sources=completed_sources,
                collected_candidates=len(candidate_sources),
            )

        await asyncio.gather(*(worker(url) for url in self.sources))

        ranked = sorted(
            candidate_sources,
            key=lambda proxy: (
                -len(candidate_sources[proxy]),
                -(
                    self.records[proxy].successful_checks
                    if proxy in self.records
                    else 0
                ),
                self.records[proxy].consecutive_failures
                if proxy in self.records
                else 0,
                proxy,
            ),
        )[: self.config.max_candidates]

        trimmed: Dict[str, Set[str]] = {}
        for proxy in ranked:
            trimmed[proxy] = candidate_sources[proxy]
            record = self.records.setdefault(proxy, ProxyRecord(proxy=proxy))
            record.add_sources(candidate_sources[proxy])

        self._emit_progress(
            phase="collect_complete",
            total_sources=total_sources,
            completed_sources=completed_sources,
            collected_candidates=len(trimmed),
        )
        return trimmed

    def _needs_recheck(self, record: ProxyRecord) -> bool:
        return (
            utc_now() - record.last_checked
        ).total_seconds() >= self.config.verify_interval

    def _select_collect_batch(
        self, candidate_sources: Dict[str, Set[str]]
    ) -> List[str]:
        batch: List[str] = []
        for proxy in candidate_sources:
            record = self.records.get(proxy)
            if (
                record is None
                or proxy not in self.active_proxies
                or self._needs_recheck(record)
            ):
                batch.append(proxy)
        return batch[: self.config.max_candidates]

    def _select_reverify_batch(self, exclude: Optional[Set[str]] = None) -> List[str]:
        excluded = exclude or set()
        records = [
            self.records[proxy]
            for proxy in self.active_proxies
            if proxy in self.records and proxy not in excluded
        ]
        records.sort(
            key=lambda item: (item.last_checked.timestamp(), -item.score, item.proxy)
        )
        return [record.proxy for record in records[: self.config.verify_batch_size]]

    async def verify_proxies(self, proxies: Sequence[str]) -> List[ProbeOutcome]:
        if not self.session:
            raise RuntimeError("harvester session is not ready")

        semaphore = asyncio.Semaphore(self.config.max_concurrent)
        outcomes: List[ProbeOutcome] = []
        total = len(proxies)
        verified = 0
        working = 0

        self._emit_progress(
            phase="verifying_proxies",
            total_verify=total,
            verified_count=0,
            working_count=0,
        )

        async def worker(proxy: str) -> None:
            nonlocal verified, working
            async with semaphore:
                if self.session is None:
                    return
                outcome = await probe_proxy(
                    session=self.session,  # type: ignore[arg-type]
                    proxy=proxy,
                    test_urls=self.config.test_urls,
                    timeout_seconds=self.config.verify_timeout,
                    user_agent=self.config.user_agent,
                )
                record = self.records.setdefault(proxy, ProxyRecord(proxy=proxy))
                if outcome.working:
                    record.record_success(
                        outcome.response_time,
                        outcome.probe_url,
                        outcome.origin,
                        self.config.max_response_time,
                    )
                    working += 1
                else:
                    record.record_failure(
                        outcome.error, outcome.probe_url, self.config.max_response_time
                    )
                outcomes.append(outcome)
                verified += 1
                self._emit_progress(
                    phase="verifying_proxies",
                    current_proxy=proxy,
                    total_verify=total,
                    verified_count=verified,
                    working_count=working,
                    active_now=len(self.active_proxies),
                )

        await asyncio.gather(*(worker(proxy) for proxy in proxies))
        self._rebuild_active_proxies()
        self._emit_progress(
            phase="verify_complete",
            total_verify=total,
            verified_count=verified,
            working_count=working,
            active_now=len(self.active_proxies),
        )
        return outcomes

    def _prune_records(self) -> None:
        stale_seconds = max(self.config.stale_after_seconds * 2.0, 3600.0)
        remove: List[str] = []

        for proxy, record in self.records.items():
            if proxy in self.active_proxies:
                continue
            age = (utc_now() - record.last_checked).total_seconds()
            if record.successful_checks == 0 and record.total_checks >= 2:
                remove.append(proxy)
            elif (
                age >= stale_seconds
                and record.consecutive_failures >= self.config.max_consecutive_failures
            ):
                remove.append(proxy)

        for proxy in remove:
            self.records.pop(proxy, None)

        if len(self.records) > self.config.max_stored_records:
            inactive = [
                (proxy, record)
                for proxy, record in self.records.items()
                if proxy not in self.active_proxies
            ]
            inactive.sort(
                key=lambda x: (
                    x[1].score,
                    x[1].last_checked.timestamp(),
                )
            )
            excess = len(self.records) - self.config.max_stored_records
            for proxy, _ in inactive[:excess]:
                self.records.pop(proxy, None)

    async def run_cycle(
        self, force_collect: bool = False, force_verify: bool = False
    ) -> Dict[str, Any]:
        summary: Dict[str, Any] = {
            "did_collect": False,
            "did_verify": False,
            "collected_candidates": 0,
            "verified_proxies": 0,
            "active_proxies": len(self.active_proxies),
            "added_active": 0,
            "removed_active": 0,
        }
        previous_active = set(self.active_proxies)
        verified_now: Set[str] = set()
        now = time.monotonic()

        self._emit_progress(
            phase="cycle_start",
            active_now=len(self.active_proxies),
        )

        if force_collect or (now - self._last_collect) >= self.config.update_interval:
            candidates = await self.collect_candidates()
            summary["did_collect"] = True
            summary["collected_candidates"] = len(candidates)
            batch = self._select_collect_batch(candidates)
            if batch:
                outcomes = await self.verify_proxies(batch)
                summary["verified_proxies"] += len(outcomes)
                verified_now.update(outcome.proxy for outcome in outcomes)
            self._last_collect = time.monotonic()

        now = time.monotonic()
        if force_verify or (now - self._last_verify) >= self.config.verify_interval:
            batch = self._select_reverify_batch(exclude=verified_now)
            if batch:
                outcomes = await self.verify_proxies(batch)
                summary["verified_proxies"] += len(outcomes)
            summary["did_verify"] = True
            self._last_verify = time.monotonic()

        self._prune_records()
        self._rebuild_active_proxies()
        await self._enrich_pool()
        summary["active_proxies"] = len(self.active_proxies)
        summary["added_active"] = len(self.active_proxies - previous_active)
        summary["removed_active"] = len(previous_active - self.active_proxies)

        best = self.best_proxy()
        if best:
            summary["best_proxy"] = best.proxy
            summary["best_score"] = best.score
            summary["best_response_time"] = best.avg_response_time

        self.save_pool()
        self._emit_progress(
            phase="cycle_complete",
            active_now=summary["active_proxies"],
            collected_candidates=summary["collected_candidates"],
            verified_count=summary["verified_proxies"],
            added_active=summary["added_active"],
            removed_active=summary["removed_active"],
            best_proxy=summary.get("best_proxy", ""),
        )
        return summary
