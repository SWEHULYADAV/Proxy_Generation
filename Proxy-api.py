#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import json
import random
import socket
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
import aiohttp_socks

# --- User-Agent Handling ---
def get_random_user_agent() -> str:
    """
    Generates thousands of unique, MODERN user-agents dynamically.
    This avoids getting blocked by using outdated versions (like Chrome 48) 
    that some libraries generate.
    """
    os_type = random.choice(["windows", "mac", "linux"])
    
    if os_type == "windows":
        os_str = "Windows NT 10.0; Win64; x64"
    elif os_type == "mac":
        mac_vers = ["10_15_7", "11_6", "12_5", "13_4", "14_0", "14_3", "14_4"]
        os_str = f"Macintosh; Intel Mac OS X {random.choice(mac_vers)}"
    else:
        os_str = "X11; Linux x86_64"

    browser = random.choices(["chrome", "firefox", "safari"], weights=[60, 20, 20], k=1)[0]

    if browser == "chrome":
        # Chrome 115-136 (current as of 2025)
        major = random.randint(115, 136)
        minor = random.randint(0, 9999)
        patch = random.randint(0, 210)
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{minor}.{patch} Safari/537.36"

    elif browser == "firefox":
        # Firefox 115-134 (current as of 2025)
        major = random.randint(115, 134)
        minor = random.randint(0, 3)
        version = f"{major}.{minor}" if minor > 0 else f"{major}.0"
        return f"Mozilla/5.0 ({os_str}; rv:{version}) Gecko/20100101 Firefox/{version}"

    else:  # Safari
        if os_type != "mac":
            os_str = "Macintosh; Intel Mac OS X 14_7"
        webkit = f"605.1.{random.randint(10, 15)}"
        version = f"{random.randint(17, 18)}.{random.randint(0, 4)}"
        return f"Mozilla/5.0 ({os_str}) AppleWebKit/{webkit} (KHTML, like Gecko) Version/{version} Safari/{webkit}"
# ---------------------------


from proxy_core import (
    DEFAULT_SOURCES,
    DEFAULT_TEST_URLS,
    HarvesterConfig,
    ProxyHarvester,
    read_source_file,
    run_async_entrypoint,
    to_iso,
    utc_now,
)

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "host",
}


def parse_proxy_url(proxy_str: str) -> str:
    proxy_str = proxy_str.strip()

    if not proxy_str:
        return f"http://{proxy_str}"

    if "://" in proxy_str:
        protocol, rest = proxy_str.split("://", 1)
        protocol = protocol.lower()

        if protocol in ("socks4", "socks5"):
            return f"{protocol}://{rest}"

        if protocol in ("http", "https"):
            return f"http://{rest}"

    return f"http://{proxy_str}"


def create_proxy_connector(proxy_url: str, max_concurrent: int = 10):
    if proxy_url.startswith("socks5://"):
        host_port = proxy_url.replace("socks5://", "")
        return aiohttp_socks.ProxyConnector.from_url(
            f"socks5://{host_port}", limit=max_concurrent
        )
    elif proxy_url.startswith("socks4://"):
        host_port = proxy_url.replace("socks4://", "")
        return aiohttp_socks.ProxyConnector.from_url(
            f"socks4://{host_port}", limit=max_concurrent
        )
    else:
        return aiohttp.TCPConnector(limit=max_concurrent, ssl=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local proxy API service that fetches target URLs through the best active free proxies."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Bind host for the local API"
    )
    parser.add_argument(
        "--port", type=int, default=8080, help="Bind port for the local API"
    )
    parser.add_argument(
        "--public-base-url",
        help="Optional public base URL if this API is exposed via domain/tunnel",
    )
    parser.add_argument(
        "--output-root",
        default="output",
        help="Root folder where each API run gets its own timestamped directory",
    )
    parser.add_argument(
        "--session-prefix", default="api", help="Per-run output folder prefix"
    )
    parser.add_argument(
        "--output",
        default="active_proxies.json",
        help="Active pool JSON filename inside the run folder",
    )
    parser.add_argument(
        "--status-file",
        default="session_info.json",
        help="Session metadata JSON filename inside the run folder",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=120,
        help="Concurrent source fetches and proxy checks",
    )
    parser.add_argument(
        "--fetch-timeout", type=float, default=8.0, help="Timeout for source downloads"
    )
    parser.add_argument(
        "--verify-timeout", type=float, default=8.0, help="Timeout for proxy validation"
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=20.0,
        help="Timeout for target URL fetches",
    )
    parser.add_argument(
        "--request-concurrency",
        type=int,
        default=80,
        help="Concurrent outbound target fetches handled by the API",
    )
    parser.add_argument(
        "--refresh-delay",
        type=float,
        default=5.0,
        help="Seconds between refresh-loop checks",
    )
    parser.add_argument(
        "--update-interval",
        type=float,
        default=120.0,
        help="Seconds between source refresh cycles",
    )
    parser.add_argument(
        "--verify-interval",
        type=float,
        default=60.0,
        help="Seconds between active proxy re-checks",
    )
    parser.add_argument(
        "--auto-save-interval",
        type=float,
        default=15.0,
        help="Minimum seconds between JSON writes",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=1000,
        help="Maximum candidates retained per source cycle",
    )
    parser.add_argument(
        "--verify-batch-size",
        type=int,
        default=120,
        help="How many active proxies to re-check per cycle",
    )
    parser.add_argument(
        "--min-success-rate",
        type=float,
        default=0.35,
        help="Drop proxies below this success rate",
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=3,
        help="Max consecutive failures before proxy removal",
    )
    parser.add_argument(
        "--stale-after",
        type=float,
        default=1800.0,
        help="Remove proxies with no success for this many seconds",
    )
    parser.add_argument(
        "--max-response-time",
        type=float,
        default=12.0,
        help="Exclude proxies slower than this average",
    )
    parser.add_argument(
        "--probe-url",
        action="append",
        dest="probe_urls",
        help="Override/add HTTP probe URL",
    )
    parser.add_argument(
        "--source-file", help="Optional file with extra source URLs, one per line"
    )
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Complete one full pool refresh before accepting traffic",
    )
    parser.add_argument(
        "--proxy-delay",
        type=float,
        default=0.5,
        help="Delay between proxy attempts in fetch mode (seconds)",
    )
    parser.add_argument(
        "--rotate-ua",
        action="store_true",
        default=True,
        help="Rotate User-Agent for each request",
    )
    parser.add_argument(
        "--no-rotate-ua",
        action="store_false",
        dest="rotate_ua",
        help="Disable User-Agent rotation",
    )
    parser.add_argument(
        "--no-shuffle-proxies",
        action="store_false",
        dest="shuffle_proxies",
        help="Try top-ranked proxies in order instead of shuffling",
    )
    parser.add_argument(
        "--tunnel-port",
        type=int,
        default=5226,
        help="Port for the standard HTTP proxy tunnel (set 0 to disable)",
    )
    parser.add_argument(
        "--tunnel-host",
        default="127.0.0.1",
        help="Bind host for the proxy tunnel",
    )
    parser.add_argument(
        "--tunnel-max-attempts",
        type=int,
        default=5,
        help="Max upstream proxy attempts per tunnel request",
    )
    parser.add_argument(
        "--tunnel-relay-timeout",
        type=float,
        default=120.0,
        help="Idle timeout for CONNECT tunnel relay in seconds",
    )
    return parser


def build_sources(extra_source_file: str | None) -> List[str]:
    sources = list(DEFAULT_SOURCES)
    for source in read_source_file(extra_source_file):
        if source not in sources:
            sources.append(source)
    return sources


def build_config(args: argparse.Namespace) -> HarvesterConfig:
    return HarvesterConfig(
        max_concurrent=args.max_concurrent,
        fetch_timeout=args.fetch_timeout,
        verify_timeout=args.verify_timeout,
        update_interval=args.update_interval,
        verify_interval=args.verify_interval,
        auto_save_interval=args.auto_save_interval,
        max_candidates=args.max_candidates,
        verify_batch_size=args.verify_batch_size,
        min_success_rate=args.min_success_rate,
        max_consecutive_failures=args.max_failures,
        stale_after_seconds=args.stale_after,
        max_response_time=args.max_response_time,
        output_file=args.output,
        test_urls=list(args.probe_urls or DEFAULT_TEST_URLS),
        max_stored_records=args.max_candidates * 2,
    )


def prepare_session(args: argparse.Namespace) -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=True)

    session_dir = root / f"{args.session_prefix}_{timestamp}"
    counter = 1
    while session_dir.exists():
        session_dir = root / f"{args.session_prefix}_{timestamp}_{counter}"
        counter += 1
    session_dir.mkdir(parents=True, exist_ok=False)

    args.output = str((session_dir / Path(args.output).name).resolve())
    args.status_file = str((session_dir / Path(args.status_file).name).resolve())
    args.session_dir = str(session_dir.resolve())
    (root / "latest_api_session.txt").write_text(args.session_dir, encoding="utf-8")
    return session_dir


def detect_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def build_access_urls(
    host: str, port: int, public_base_url: str | None = None
) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    if host in {"0.0.0.0", "::"}:
        urls["local"] = f"http://127.0.0.1:{port}"
        lan_ip = detect_lan_ip()
        if lan_ip and lan_ip != "127.0.0.1":
            urls["lan"] = f"http://{lan_ip}:{port}"
    else:
        urls["local"] = f"http://{host}:{port}"

    if public_base_url:
        urls["public"] = public_base_url.rstrip("/")
    return urls


def sanitize_outbound_headers(headers: Dict[str, str]) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in HOP_BY_HOP_HEADERS:
            continue
        cleaned[key] = value
    return cleaned


def sanitize_inbound_response_headers(
    headers: "aiohttp.typedefs.LooseHeaders",
) -> Dict[str, str]:
    cleaned: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in HOP_BY_HOP_HEADERS:
            continue
        cleaned[key] = value
    return cleaned


def is_valid_target_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class ProxyAPIService:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.session_dir = prepare_session(args)
        self.sources = build_sources(args.source_file)
        self.config = build_config(args)
        self.access_urls = build_access_urls(args.host, args.port, args.public_base_url)
        self.progress: Dict[str, Any] = {"phase": "starting"}
        self.last_summary: Dict[str, Any] = {"active_proxies": 0}
        self.last_refresh_at: str = ""
        self.refresh_lock = asyncio.Lock()
        self.ready_event = asyncio.Event()
        self.harvester: Optional[ProxyHarvester] = None
        self.request_session: Optional[aiohttp.ClientSession] = None
        self.refresh_task: Optional[asyncio.Task] = None
        # session_id -> last-used proxy URL (sticky-session support)
        self._sticky_sessions: Dict[str, str] = {}

    def on_progress(self, payload: Dict[str, Any]) -> None:
        self.progress.update(payload)
        self._write_status_file()

    def _write_status_file(self) -> None:
        payload = self.status_payload(include_proxies=False)
        Path(self.args.status_file).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    async def start(self) -> None:
        self.harvester = await ProxyHarvester(
            config=self.config,
            sources=self.sources,
            progress_callback=self.on_progress,
        ).__aenter__()
        connector = aiohttp.TCPConnector(limit=self.args.request_concurrency, ssl=True)
        timeout = aiohttp.ClientTimeout(total=self.args.request_timeout)
        self.request_session = aiohttp.ClientSession(
            connector=connector, timeout=timeout, trust_env=False
        )
        self._write_status_file()

        if self.args.warmup:
            await self.refresh_once(force_collect=True, force_verify=True)
            self.ready_event.set()

        self.refresh_task = asyncio.create_task(
            self._refresh_loop(), name="proxy-api-refresh"
        )

    async def stop(self) -> None:
        if self.refresh_task:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass

        if self.request_session:
            await self.request_session.close()
            self.request_session = None

        if self.harvester:
            await self.harvester.__aexit__(None, None, None)
            self.harvester = None

    async def _refresh_loop(self) -> None:
        first_cycle = not self.args.warmup
        try:
            while True:
                await self.refresh_once(
                    force_collect=first_cycle, force_verify=first_cycle
                )
                self.ready_event.set()
                first_cycle = False
                await asyncio.sleep(self.args.refresh_delay)
        except asyncio.CancelledError:
            raise

    async def refresh_once(
        self, force_collect: bool = False, force_verify: bool = False
    ) -> Dict[str, Any]:
        if not self.harvester:
            raise RuntimeError("harvester is not initialized")
        async with self.refresh_lock:
            summary = await self.harvester.run_cycle(
                force_collect=force_collect, force_verify=force_verify
            )
            self.last_summary = summary
            self.last_refresh_at = to_iso(utc_now())
            self._write_status_file()
            return summary

    def ranked_records(
        self,
        limit: int = 50,
        min_score: float = 0.0,
        protocol: Optional[str] = None,
        country: Optional[str] = None,
        anonymity: Optional[str] = None,
    ):
        if not self.harvester:
            return []
        return self.harvester._filtered_records(
            protocol=protocol,
            country=country,
            anonymity=anonymity,
            min_score=min_score,
            limit=limit,
        )

    async def ensure_ready(self) -> None:
        if self.harvester and self.harvester.active_proxies:
            return
        await self.refresh_once(force_collect=True, force_verify=True)
        self.ready_event.set()

    def status_payload(
        self, include_proxies: bool = False, limit: int = 20
    ) -> Dict[str, Any]:
        best_proxy = ""
        if self.harvester:
            best = self.harvester.best_proxy()
            if best:
                best_proxy = best.proxy

        payload: Dict[str, Any] = {
            "ok": True,
            "session_dir": self.args.session_dir,
            "updated_at": to_iso(utc_now()),
            "last_refresh_at": self.last_refresh_at,
            "sources_count": len(self.sources),
            "active_proxies": len(self.harvester.active_proxies)
            if self.harvester
            else 0,
            "known_records": len(self.harvester.records) if self.harvester else 0,
            "best_proxy": best_proxy,
            "access_urls": self.access_urls,
            "progress": self.progress,
            "files": {
                "active_pool_json": self.args.output,
                "status_json": self.args.status_file,
            },
            "last_summary": self.last_summary,
        }
        if include_proxies:
            payload["proxies"] = [
                record.to_dict() for record in self.ranked_records(limit=limit)
            ]
        return payload

    async def fetch_via_proxies(
        self,
        *,
        target_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        timeout: Optional[float] = None,
        max_attempts: int = 10,
        expected_status: Optional[int] = None,
        pool_limit: int = 50,
        min_score: float = 0.0,
        allow_redirects: bool = True,
        session_id: Optional[str] = None,
        min_proxy_interval: float = 0.0,
    ) -> Dict[str, Any]:
        if not self.harvester or not self.request_session:
            raise RuntimeError("service not started")

        await self.ensure_ready()
        records = self.ranked_records(limit=pool_limit, min_score=min_score)
        if not records:
            await self.refresh_once(force_collect=True, force_verify=True)
            records = self.ranked_records(limit=pool_limit, min_score=min_score)
        if not records:
            return {
                "ok": False,
                "error": "no active proxies available",
                "attempts": [],
            }

        # Sticky session: move previously-used proxy to front
        if session_id:
            preferred_url = self._sticky_sessions.get(session_id)
            if preferred_url:
                preferred = [r for r in records if r.proxy == preferred_url]
                others = [r for r in records if r.proxy != preferred_url]
                records = preferred + others

        # Skip proxies on cooldown (per-proxy rate limiting)
        if min_proxy_interval > 0:
            records = [r for r in records if not r.on_cooldown(min_proxy_interval)] or records

        attempts: List[Dict[str, Any]] = []
        timeout_config = aiohttp.ClientTimeout(
            total=timeout or self.args.request_timeout
        )

        shuffle_proxy = getattr(self.args, "shuffle_proxies", True)
        rotate_ua = getattr(self.args, "rotate_ua", True)
        proxy_delay = getattr(self.args, "proxy_delay", 0.5)

        # When sticky session is active, don't shuffle (preserve priority)
        if shuffle_proxy and not session_id:
            shuffled = list(records[: max_attempts * 2])
            random.shuffle(shuffled)
            records_to_try = shuffled[:max_attempts]
        else:
            records_to_try = records[:max_attempts]

        for index, record in enumerate(records_to_try, start=1):
            proxy_url = parse_proxy_url(record.proxy)

            headers_for_request = sanitize_outbound_headers(headers or {})

            if rotate_ua:
                headers_for_request["User-Agent"] = get_random_user_agent()

            session = self.request_session
            close_session = False
            request_kwargs = {
                "method": method.upper(),
                "url": target_url,
                "headers": headers_for_request,
                "data": body,
                "timeout": timeout_config,
                "allow_redirects": allow_redirects,
            }

            try:
                if proxy_url.startswith("socks"):
                    connector = create_proxy_connector(proxy_url, max_concurrent=1)
                    session = aiohttp.ClientSession(
                        connector=connector,
                        timeout=timeout_config,
                        trust_env=False,
                    )
                    close_session = True
                else:
                    request_kwargs["proxy"] = proxy_url

                async with session.request(**request_kwargs) as response:
                    payload_bytes = await response.read()
                    attempt = {
                        "attempt": index,
                        "proxy": record.proxy,
                        "proxy_url": proxy_url,
                        "score": record.score,
                        "status_code": response.status,
                        "final_url": str(response.url),
                    }
                    if (
                        expected_status is not None
                        and response.status != expected_status
                    ):
                        attempt["error"] = (
                            f"expected {expected_status}, got {response.status}"
                        )
                        attempts.append(attempt)
                        if proxy_delay > 0:
                            await asyncio.sleep(proxy_delay)
                        continue

                    record.mark_used()
                    if session_id:
                        if len(self._sticky_sessions) > 10_000:
                            self._sticky_sessions.clear()
                        self._sticky_sessions[session_id] = record.proxy
                    return {
                        "ok": True,
                        "proxy": record.proxy,
                        "proxy_url": proxy_url,
                        "proxy_score": record.score,
                        "proxy_country": record.country,
                        "proxy_anonymity": record.anonymity,
                        "proxy_protocol": record.protocol,
                        "attempts": attempts + [attempt],
                        "status_code": response.status,
                        "reason": response.reason,
                        "final_url": str(response.url),
                        "headers": dict(response.headers),
                        "body_bytes": payload_bytes,
                        "body_text": payload_bytes.decode("utf-8", errors="replace"),
                    }
            except Exception as exc:
                attempts.append(
                    {
                        "attempt": index,
                        "proxy": record.proxy,
                        "proxy_url": proxy_url,
                        "score": record.score,
                        "error": exc.__class__.__name__,
                    }
                )

                if proxy_delay > 0:
                    await asyncio.sleep(proxy_delay)
            finally:
                if close_session and session is not None:
                    try:
                        await session.close()
                    except Exception:
                        pass

        return {
            "ok": False,
            "error": "all proxy attempts failed",
            "attempts": attempts,
        }


# ---------------------------------------------------------------------------
#  Proxy Tunnel – Standard HTTP Forward Proxy
# ---------------------------------------------------------------------------

TUNNEL_BUFFER_SIZE = 65536


class ProxyTunnel:
    """Standard HTTP forward proxy that automatically routes traffic through
    the best available upstream proxy with rotation and retry.

    Usage in Python (requests)::

        proxies = {"http": "http://localhost:8888", "https": "http://localhost:8888"}
        requests.get("https://example.com", proxies=proxies)

    Usage with curl::

        curl -x http://localhost:8888 https://example.com

    For HTTPS targets the client sends a CONNECT request.  The tunnel opens
    a TCP connection to the best upstream HTTP proxy, issues its own CONNECT,
    and relays bytes bidirectionally once the upstream handshake succeeds.

    For plain HTTP targets the full-URL request is forwarded through the
    existing ``fetch_via_proxies`` infrastructure.
    """

    def __init__(
        self,
        service: "ProxyAPIService",
        host: str = "127.0.0.1",
        port: int = 8888,
        max_attempts: int = 5,
        connect_timeout: float = 15.0,
        relay_timeout: float = 120.0,
        rotate_ua: bool = True,
    ):
        self.service = service
        self.host = host
        self.port = port
        self.max_attempts = max_attempts
        self.connect_timeout = connect_timeout
        self.relay_timeout = relay_timeout
        self.rotate_ua = rotate_ua
        self._server: Optional[asyncio.Server] = None
        self._stats: Dict[str, int] = {
            "total_requests": 0,
            "connect_requests": 0,
            "http_requests": 0,
            "successful": 0,
            "failed": 0,
        }

    @property
    def stats(self) -> Dict[str, int]:
        return dict(self._stats)

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def _pick_proxies(self) -> list:
        """Return a shuffled selection of the best active proxies."""
        records = self.service.ranked_records(
            limit=self.max_attempts * 2, min_score=0.0,
        )
        if not records:
            return []
        pool = list(records[: self.max_attempts * 2])
        random.shuffle(pool)
        return pool[: self.max_attempts]

    # ---- client entry point ------------------------------------------------

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        try:
            first_line = await asyncio.wait_for(
                client_reader.readline(), timeout=self.connect_timeout,
            )
            if not first_line:
                return

            self._stats["total_requests"] += 1
            decoded = first_line.decode("latin-1", errors="replace").strip()

            if decoded.upper().startswith("CONNECT "):
                self._stats["connect_requests"] += 1
                await self._handle_connect(decoded, client_reader, client_writer)
            else:
                self._stats["http_requests"] += 1
                await self._handle_plain_http(
                    decoded, client_reader, client_writer,
                )
        except Exception:
            pass
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass

    # ---- CONNECT (HTTPS tunnel) --------------------------------------------

    async def _handle_connect(
        self,
        request_line: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        parts = request_line.split()
        if len(parts) < 2:
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_writer.drain()
            self._stats["failed"] += 1
            return

        target = parts[1]
        if ":" in target:
            target_host, port_str = target.rsplit(":", 1)
            try:
                target_port = int(port_str)
            except ValueError:
                target_port = 443
        else:
            target_host = target
            target_port = 443

        # Consume remaining request headers
        while True:
            line = await asyncio.wait_for(
                client_reader.readline(), timeout=self.connect_timeout,
            )
            if line in (b"\r\n", b"\n", b""):
                break

        proxies = self._pick_proxies()
        if not proxies:
            client_writer.write(b"HTTP/1.1 502 No Proxies Available\r\n\r\n")
            await client_writer.drain()
            self._stats["failed"] += 1
            return

        for record in proxies:
            proxy_url = parse_proxy_url(record.proxy)
            # CONNECT tunneling only works through HTTP proxies
            if proxy_url.startswith("socks"):
                continue
            try:
                ok = await self._tunnel_via_http_proxy(
                    proxy_url, target_host, target_port,
                    client_reader, client_writer,
                )
                if ok:
                    self._stats["successful"] += 1
                    return
            except Exception:
                continue

        client_writer.write(b"HTTP/1.1 502 All Proxies Failed\r\n\r\n")
        await client_writer.drain()
        self._stats["failed"] += 1

    async def _tunnel_via_http_proxy(
        self,
        proxy_url: str,
        target_host: str,
        target_port: int,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> bool:
        """Open a CONNECT tunnel through an upstream HTTP proxy."""
        stripped = proxy_url.split("://", 1)[-1]
        if ":" in stripped:
            p_host, p_port_str = stripped.rsplit(":", 1)
            p_port = int(p_port_str)
        else:
            p_host = stripped
            p_port = 8080

        up_reader, up_writer = await asyncio.wait_for(
            asyncio.open_connection(p_host, p_port),
            timeout=self.connect_timeout,
        )

        try:
            connect_req = (
                f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
                f"Host: {target_host}:{target_port}\r\n\r\n"
            ).encode()
            up_writer.write(connect_req)
            await up_writer.drain()

            resp_line = await asyncio.wait_for(
                up_reader.readline(), timeout=self.connect_timeout,
            )
            # Consume remaining upstream response headers
            while True:
                hdr = await asyncio.wait_for(
                    up_reader.readline(), timeout=self.connect_timeout,
                )
                if hdr in (b"\r\n", b"\n", b""):
                    break

            if b"200" not in resp_line:
                up_writer.close()
                return False

            # Inform client that the tunnel is established
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()

            # Bidirectional relay
            await self._relay(client_reader, client_writer, up_reader, up_writer)
            return True
        except Exception:
            try:
                up_writer.close()
            except Exception:
                pass
            return False

    async def _relay(
        self,
        r1: asyncio.StreamReader,
        w1: asyncio.StreamWriter,
        r2: asyncio.StreamReader,
        w2: asyncio.StreamWriter,
    ) -> None:
        """Bidirectional data relay between client and upstream."""

        async def _pipe(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
        ) -> None:
            try:
                while True:
                    data = await asyncio.wait_for(
                        reader.read(TUNNEL_BUFFER_SIZE),
                        timeout=self.relay_timeout,
                    )
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
            except (
                asyncio.TimeoutError,
                ConnectionResetError,
                BrokenPipeError,
                OSError,
            ):
                pass
            finally:
                try:
                    writer.close()
                except Exception:
                    pass

        t1 = asyncio.create_task(_pipe(r1, w2))
        t2 = asyncio.create_task(_pipe(r2, w1))
        done, pending = await asyncio.wait(
            {t1, t2}, return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass

    # ---- Plain HTTP forwarding ---------------------------------------------

    async def _handle_plain_http(
        self,
        request_line: str,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        """Forward a plain HTTP request through the proxy pool."""
        parts = request_line.split(None, 2)
        if len(parts) < 3:
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_writer.drain()
            self._stats["failed"] += 1
            return

        method, target_url = parts[0], parts[1]
        if not is_valid_target_url(target_url):
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_writer.drain()
            self._stats["failed"] += 1
            return

        headers: Dict[str, str] = {}
        content_length = 0
        while True:
            hdr = await asyncio.wait_for(
                client_reader.readline(), timeout=self.connect_timeout,
            )
            if hdr in (b"\r\n", b"\n", b""):
                break
            decoded = hdr.decode("latin-1", errors="replace").strip()
            if ":" in decoded:
                k, v = decoded.split(":", 1)
                k, v = k.strip(), v.strip()
                if k.lower() == "content-length":
                    content_length = int(v)
                if k.lower() not in HOP_BY_HOP_HEADERS:
                    headers[k] = v

        body: Optional[bytes] = None
        if content_length > 0:
            body = await asyncio.wait_for(
                client_reader.readexactly(content_length),
                timeout=self.connect_timeout,
            )

        if self.rotate_ua:
            headers["User-Agent"] = get_random_user_agent()

        result = await self.service.fetch_via_proxies(
            target_url=target_url,
            method=method,
            headers=headers,
            body=body,
            max_attempts=self.max_attempts,
        )

        if not result.get("ok"):
            err_body = json.dumps(
                {"error": result.get("error", "proxy failed")},
            ).encode()
            resp = (
                f"HTTP/1.1 502 Bad Gateway\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {len(err_body)}\r\n\r\n"
            ).encode() + err_body
            client_writer.write(resp)
            await client_writer.drain()
            self._stats["failed"] += 1
            return

        status = result.get("status_code", 200)
        reason = result.get("reason", "OK")
        resp_body: bytes = result.get("body_bytes", b"")
        resp_headers = sanitize_inbound_response_headers(result.get("headers", {}))
        resp_headers["Content-Length"] = str(len(resp_body))
        resp_headers["X-Proxy-Used"] = result.get("proxy", "")

        header_block = "".join(f"{k}: {v}\r\n" for k, v in resp_headers.items())
        client_writer.write(
            f"HTTP/1.1 {status} {reason}\r\n{header_block}\r\n".encode()
        )
        client_writer.write(resp_body)
        await client_writer.drain()
        self._stats["successful"] += 1


async def parse_fetch_request(
    request: web.Request, *, default_method: Optional[str] = None
) -> Dict[str, Any]:
    if request.method == "GET":
        return {
            "url": request.query.get("url", "").strip(),
            "method": request.query.get("method", default_method or "GET"),
            "timeout": float(request.query.get("timeout", "0") or 0) or None,
            "max_attempts": int(request.query.get("max_attempts", "10")),
            "expected_status": int(request.query["expected_status"])
            if "expected_status" in request.query
            else None,
            "pool_limit": int(request.query.get("pool_limit", "50")),
            "min_score": float(request.query.get("min_score", "0")),
            "allow_redirects": request.query.get("allow_redirects", "true").lower()
            != "false",
            "session_id": request.query.get("session_id") or None,
            "min_proxy_interval": float(request.query.get("min_proxy_interval", "0")),
            "headers": {},
            "body": None,
        }

    if request.content_type == "application/json":
        payload = await request.json()
        body_value = payload.get("body")
        if isinstance(body_value, str):
            body_bytes = body_value.encode("utf-8")
        elif body_value is None:
            body_bytes = None
        else:
            body_bytes = json.dumps(body_value).encode("utf-8")
        return {
            "url": str(payload.get("url", "")).strip(),
            "method": str(payload.get("method", default_method or request.method)),
            "timeout": float(payload["timeout"]) if payload.get("timeout") else None,
            "max_attempts": int(payload.get("max_attempts", 10)),
            "expected_status": int(payload["expected_status"])
            if payload.get("expected_status") is not None
            else None,
            "pool_limit": int(payload.get("pool_limit", 50)),
            "min_score": float(payload.get("min_score", 0)),
            "allow_redirects": bool(payload.get("allow_redirects", True)),
            "session_id": str(payload["session_id"]) if payload.get("session_id") else None,
            "min_proxy_interval": float(payload.get("min_proxy_interval", 0)),
            "headers": {
                str(k): str(v) for k, v in dict(payload.get("headers", {})).items()
            },
            "body": body_bytes,
        }

    raw_body = await request.read()
    return {
        "url": request.query.get("url", "").strip(),
        "method": request.query.get("method", default_method or request.method),
        "timeout": float(request.query.get("timeout", "0") or 0) or None,
        "max_attempts": int(request.query.get("max_attempts", "10")),
        "expected_status": int(request.query["expected_status"])
        if "expected_status" in request.query
        else None,
        "pool_limit": int(request.query.get("pool_limit", "50")),
        "min_score": float(request.query.get("min_score", "0")),
        "allow_redirects": request.query.get("allow_redirects", "true").lower()
        != "false",
        "session_id": request.query.get("session_id") or None,
        "min_proxy_interval": float(request.query.get("min_proxy_interval", "0")),
        "headers": {key: value for key, value in request.headers.items()},
        "body": raw_body or None,
    }


def json_error(message: str, status: int = 400, **extra: Any) -> web.Response:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return web.json_response(payload, status=status)


async def handle_status(request: web.Request) -> web.Response:
    service: ProxyAPIService = request.app["service"]
    include_proxies = request.query.get("include_proxies", "false").lower() == "true"
    limit = int(request.query.get("limit", "20"))
    return web.json_response(
        service.status_payload(include_proxies=include_proxies, limit=limit)
    )


async def handle_tunnel_status(request: web.Request) -> web.Response:
    tunnel: Optional[ProxyTunnel] = request.app.get("tunnel")
    if not tunnel:
        return web.json_response(
            {"ok": True, "tunnel_enabled": False, "message": "tunnel is disabled (--tunnel-port 0)"},
        )
    return web.json_response({
        "ok": True,
        "tunnel_enabled": True,
        "tunnel_url": f"http://{tunnel.host}:{tunnel.port}",
        "tunnel_host": tunnel.host,
        "tunnel_port": tunnel.port,
        "max_attempts": tunnel.max_attempts,
        "stats": tunnel.stats,
    })


async def handle_proxies(request: web.Request) -> web.Response:
    service: ProxyAPIService = request.app["service"]
    limit = int(request.query.get("limit", "50"))
    min_score = float(request.query.get("min_score", "0"))
    protocol = request.query.get("protocol") or None
    country = request.query.get("country") or None
    anonymity = request.query.get("anonymity") or None
    proxies = [
        record.to_dict()
        for record in service.ranked_records(
            limit=limit,
            min_score=min_score,
            protocol=protocol,
            country=country,
            anonymity=anonymity,
        )
    ]
    return web.json_response({"ok": True, "count": len(proxies), "proxies": proxies})


async def handle_next(request: web.Request) -> web.Response:
    """Round-robin: return the next proxy matching optional filter criteria."""
    service: ProxyAPIService = request.app["service"]
    if not service.harvester:
        return json_error("service not ready", status=503)
    protocol = request.query.get("protocol") or None
    country = request.query.get("country") or None
    anonymity = request.query.get("anonymity") or None
    min_score = float(request.query.get("min_score", "0"))
    skip_cooldown = float(request.query.get("skip_cooldown", "0"))
    record = service.harvester.next_proxy(
        protocol=protocol,
        country=country,
        anonymity=anonymity,
        min_score=min_score,
        skip_cooldown=skip_cooldown,
    )
    if not record:
        return json_error("no proxy matching criteria", status=404)
    record.mark_used()
    return web.json_response({
        "ok": True,
        "proxy": record.proxy,
        "protocol": record.protocol,
        "country": record.country,
        "anonymity": record.anonymity,
        "score": round(record.score, 4),
        "avg_response_time": round(record.avg_response_time, 3),
        "success_rate": round(record.success_rate, 4),
    })


async def handle_random(request: web.Request) -> web.Response:
    """Return a random proxy matching optional filter criteria."""
    service: ProxyAPIService = request.app["service"]
    if not service.harvester:
        return json_error("service not ready", status=503)
    protocol = request.query.get("protocol") or None
    country = request.query.get("country") or None
    anonymity = request.query.get("anonymity") or None
    min_score = float(request.query.get("min_score", "0"))
    records = service.harvester._filtered_records(
        protocol=protocol, country=country, anonymity=anonymity, min_score=min_score
    )
    if not records:
        return json_error("no proxy matching criteria", status=404)
    record = random.choice(records)
    record.mark_used()
    return web.json_response({
        "ok": True,
        "proxy": record.proxy,
        "protocol": record.protocol,
        "country": record.country,
        "anonymity": record.anonymity,
        "score": round(record.score, 4),
        "avg_response_time": round(record.avg_response_time, 3),
        "success_rate": round(record.success_rate, 4),
    })


async def handle_stats(request: web.Request) -> web.Response:
    """Detailed breakdown of the active proxy pool by protocol/country/anonymity."""
    service: ProxyAPIService = request.app["service"]
    if not service.harvester:
        return json_error("service not ready", status=503)

    records = list(service.harvester.ranked_active_records())
    by_protocol: Dict[str, int] = {}
    by_country: Dict[str, int] = {}
    by_anonymity: Dict[str, int] = {}
    total_score = 0.0
    total_rtt = 0.0
    count_rtt = 0

    for r in records:
        proto = r.protocol
        by_protocol[proto] = by_protocol.get(proto, 0) + 1
        if r.country:
            by_country[r.country] = by_country.get(r.country, 0) + 1
        anon_key = r.anonymity or "unknown"
        by_anonymity[anon_key] = by_anonymity.get(anon_key, 0) + 1
        total_score += r.score
        if r.avg_response_time > 0:
            total_rtt += r.avg_response_time
            count_rtt += 1

    return web.json_response({
        "ok": True,
        "total_active": len(records),
        "by_protocol": by_protocol,
        "by_country": dict(sorted(by_country.items(), key=lambda x: -x[1])[:30]),
        "by_anonymity": by_anonymity,
        "avg_score": round(total_score / len(records), 4) if records else 0.0,
        "avg_response_time": round(total_rtt / count_rtt, 3) if count_rtt else 0.0,
        "enriched_count": sum(1 for r in records if r.anonymity),
        "geolocated_count": sum(1 for r in records if r.country),
    })


async def handle_fetch_json(request: web.Request) -> web.Response:
    service: ProxyAPIService = request.app["service"]
    options = await parse_fetch_request(request)
    target_url = options["url"]
    if not is_valid_target_url(target_url):
        return json_error("valid http/https url is required", status=400)

    result = await service.fetch_via_proxies(
        target_url=target_url,
        method=options["method"],
        headers=options["headers"],
        body=options["body"],
        timeout=options["timeout"],
        max_attempts=options["max_attempts"],
        expected_status=options["expected_status"],
        pool_limit=options["pool_limit"],
        min_score=options["min_score"],
        allow_redirects=options["allow_redirects"],
        session_id=options.get("session_id"),
        min_proxy_interval=options.get("min_proxy_interval", 0.0),
    )
    if not result["ok"]:
        return web.json_response(result, status=502)

    payload = {
        "ok": True,
        "proxy": result["proxy"],
        "proxy_score": result["proxy_score"],
        "proxy_country": result.get("proxy_country", ""),
        "proxy_anonymity": result.get("proxy_anonymity", ""),
        "proxy_protocol": result.get("proxy_protocol", ""),
        "status_code": result["status_code"],
        "reason": result["reason"],
        "final_url": result["final_url"],
        "headers": result["headers"],
        "body": result["body_text"],
        "attempts": result["attempts"],
    }
    return web.json_response(payload)


async def handle_proxy_raw(request: web.Request) -> web.Response:
    service: ProxyAPIService = request.app["service"]
    options = await parse_fetch_request(request, default_method=request.method)
    target_url = options["url"]
    if not is_valid_target_url(target_url):
        return json_error("valid http/https url is required", status=400)

    result = await service.fetch_via_proxies(
        target_url=target_url,
        method=options["method"],
        headers=options["headers"],
        body=options["body"],
        timeout=options["timeout"],
        max_attempts=options["max_attempts"],
        expected_status=options["expected_status"],
        pool_limit=options["pool_limit"],
        min_score=options["min_score"],
        allow_redirects=options["allow_redirects"],
        session_id=options.get("session_id"),
        min_proxy_interval=options.get("min_proxy_interval", 0.0),
    )
    if not result["ok"]:
        return web.json_response(result, status=502)

    headers = sanitize_inbound_response_headers(result["headers"])
    headers["X-Proxy-Used"] = result["proxy"]
    headers["X-Proxy-Score"] = str(result["proxy_score"])
    headers["X-Proxy-Attempts"] = str(len(result["attempts"]))
    headers["X-Final-URL"] = result["final_url"]
    return web.Response(
        status=result["status_code"], body=result["body_bytes"], headers=headers
    )


async def create_app(args: argparse.Namespace) -> web.Application:
    service = ProxyAPIService(args)
    app = web.Application(client_max_size=20 * 1024 * 1024)
    app["service"] = service

    async def on_startup(app: web.Application) -> None:
        await app["service"].start()

    async def on_cleanup(app: web.Application) -> None:
        await app["service"].stop()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    app.router.add_get("/", handle_status)
    app.router.add_get("/health", handle_status)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/proxies", handle_proxies)
    app.router.add_get("/next", handle_next)
    app.router.add_get("/random", handle_random)
    app.router.add_get("/stats", handle_stats)
    app.router.add_route("*", "/proxy", handle_proxy_raw)
    app.router.add_route("*", "/fetch", handle_fetch_json)
    app.router.add_get("/tunnel-status", handle_tunnel_status)
    return app


async def run_server(args: argparse.Namespace) -> None:
    app = await create_app(args)
    tunnel: Optional[ProxyTunnel] = None
    tunnel_port = getattr(args, "tunnel_port", 0)
    tunnel_host = getattr(args, "tunnel_host", args.host)

    if tunnel_port > 0:
        service: ProxyAPIService = app["service"]
        tunnel = ProxyTunnel(
            service=service,
            host=tunnel_host,
            port=tunnel_port,
            max_attempts=getattr(args, "tunnel_max_attempts", 5),
            relay_timeout=getattr(args, "tunnel_relay_timeout", 120.0),
            rotate_ua=getattr(args, "rotate_ua", True),
        )
        app["tunnel"] = tunnel

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=args.host, port=args.port)
    access_urls = build_access_urls(args.host, args.port, args.public_base_url)

    print("\n" + "=" * 60)
    print("  PROXY API SERVICE")
    print("=" * 60)
    print("\nAPI Access URLs:")
    for name, url in access_urls.items():
        print(f"  {name}: {url}")
    preferred_url = (
        access_urls.get("public")
        or access_urls.get("lan")
        or access_urls.get("local")
        or f"http://{args.host}:{args.port}"
    )
    print("\nAPI Endpoints:")
    print(f"  GET  {preferred_url}/status")
    print(f"  GET  {preferred_url}/stats                  -- pool breakdown by protocol/country/anonymity")
    print(f"  GET  {preferred_url}/proxies                -- list proxies (?protocol= &country= &anonymity= &min_score=)")
    print(f"  GET  {preferred_url}/next                   -- round-robin next proxy (?protocol= &country= &anonymity=)")
    print(f"  GET  {preferred_url}/random                 -- random proxy from pool (?protocol= &country= &anonymity=)")
    print(f"  GET  {preferred_url}/proxy?url=https://example.com  -- fetch URL through rotating proxy")
    print(f"  POST {preferred_url}/fetch                  -- JSON body: {{url, method, headers, session_id, ...}}")
    print(f"  GET  {preferred_url}/tunnel-status")

    if tunnel:
        await tunnel.start()
        print("\n" + "-" * 60)
        print("  PROXY TUNNEL (Standard Forward Proxy)")
        print("-" * 60)
        print(f"\n  Tunnel URL:  http://{tunnel_host}:{tunnel_port}")
        print(f"\n  Python usage:")
        print(f'    proxies = {{"http": "http://{tunnel_host}:{tunnel_port}", "https": "http://{tunnel_host}:{tunnel_port}"}}')
        print(f'    requests.get("https://example.com", proxies=proxies)')
        print(f"\n  curl usage:")
        print(f"    curl -x http://{tunnel_host}:{tunnel_port} https://example.com")
    else:
        print("\n  Proxy Tunnel: DISABLED (use --tunnel-port to enable)")

    print(f"\nSession folder: {args.session_dir}")
    print("=" * 60 + "\n")

    await site.start()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        if tunnel:
            await tunnel.stop()
        await runner.cleanup()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run_async_entrypoint(run_server(args))
    except KeyboardInterrupt:
        print("Proxy API stopped.")


if __name__ == "__main__":
    main()
