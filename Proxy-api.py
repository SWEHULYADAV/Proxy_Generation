#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import argparse
import base64
import hmac
import json
import logging
import random
import socket
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
import aiohttp_socks

try:
    from python_socks.async_.asyncio import Proxy as _SocksProxy
    _SOCKS_TUNNEL_OK = True
except ImportError:
    _SOCKS_TUNNEL_OK = False

logger = logging.getLogger("proxy_api")

# ---------------------------------------------------------------------------
#  Humanized Browser Fingerprint Engine
#  Covers every major device category: desktop (Windows/Mac/Linux/Ubuntu),
#  mobile (Android/iOS), tablet (iPad), Samsung Internet, Edge, Opera.
#  Each profile emits a CONSISTENT set of headers that match the UA string —
#  Sec-CH-UA-Mobile, platform, accept-encoding, DNT, etc. are all coherent.
# ---------------------------------------------------------------------------

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9", "en-GB,en;q=0.9", "en-CA,en;q=0.9", "en-AU,en;q=0.9",
    "en-US,en;q=0.9,es;q=0.8", "en-US,en;q=0.9,fr;q=0.8",
    "en-US,en;q=0.9,de;q=0.8", "en-US,en;q=0.8,zh-CN;q=0.6",
    "en-US,en;q=0.9,pt;q=0.8", "en-IN,en-GB;q=0.9,en;q=0.8",
    "en-US,en;q=0.9,ja;q=0.7", "en-US,en;q=0.9,ko;q=0.7",
    "en-ZA,en;q=0.9", "en-PH,en;q=0.9", "en-NG,en;q=0.8",
]

_CHROME_ACCEPT    = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
_FIREFOX_ACCEPT   = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
_SAFARI_ACCEPT    = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
_EDGE_ACCEPT      = "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"

# Desktop OS strings
_WIN_OS   = ["Windows NT 10.0; Win64; x64", "Windows NT 10.0; WOW64", "Windows NT 11.0; Win64; x64"]
_MAC_OS   = ["10_15_7", "11_6_8", "12_6_9", "13_5_2", "13_6_4", "14_2_1", "14_4_1", "14_5", "14_6_1", "15_0"]
_LNX_OS   = ["X11; Linux x86_64", "X11; Ubuntu; Linux x86_64", "X11; Fedora; Linux x86_64",
             "X11; Linux i686", "X11; CrOS x86_64 15117.111.0"]

# Mobile OS strings
_ANDROID_VER = ["10", "11", "12", "13", "14", "15"]
_ANDROID_MODELS = [
    "Pixel 6", "Pixel 7", "Pixel 8", "Pixel 8 Pro", "Pixel 9",
    "SM-G991B", "SM-S901B", "SM-S921B", "SM-A546B", "SM-A336B",
    "motorola edge 40", "motorola moto g84", "OnePlus 12", "OnePlus Nord 3",
    "POCO F5", "Redmi Note 12 Pro", "Xiaomi 13", "Xiaomi 14 Pro",
    "vivo V29", "OPPO Reno10 Pro", "realme GT 5", "Nokia G60",
]
_IOS_VER    = ["16_6_1", "17_0", "17_1_1", "17_2", "17_3_1", "17_4", "17_5", "17_6", "18_0", "18_1"]
_IPHONE_MDL = ["iPhone14,2", "iPhone14,3", "iPhone15,2", "iPhone15,3", "iPhone16,1", "iPhone16,2"]
_IPAD_MDL   = ["iPad13,4", "iPad13,18", "iPad14,1", "iPad14,5", "iPad16,3"]

# Browser versions
_CHROME_VER  = list(range(116, 137))
_FIREFOX_VER = list(range(115, 135))
_EDGE_VER    = list(range(110, 130))
_SAMSUNG_VER = ["23.0", "24.0", "25.0", "26.0"]
_OPERA_VER   = ["106", "107", "108", "109", "110"]
_SAFARI_WK   = [f"605.1.{i}" for i in range(10, 16)]
_SAFARI_VER  = ["16.6", "17.0", "17.1", "17.2", "17.3", "17.4", "17.5", "18.0", "18.1", "18.2"]


def _not_brand(major: int) -> str:
    return f'"Not_A Brand";v="8", "Chromium";v="{major}", "Google Chrome";v="{major}"'


def _not_brand_edge(major: int) -> str:
    return f'"Not A;Brand";v="99", "Chromium";v="{major}", "Microsoft Edge";v="{major}"'


def _not_brand_samsung(major_str: str) -> str:
    chrome_approx = 120
    return f'"Not_A Brand";v="8", "Chromium";v="{chrome_approx}", "Samsung Internet";v="{major_str}"'


def _build_desktop_chrome() -> Dict[str, str]:
    os_type = random.choices(["windows", "mac", "linux"], weights=[65, 25, 10], k=1)[0]
    if os_type == "windows":
        os_str, platform = random.choice(_WIN_OS), "Windows"
    elif os_type == "mac":
        os_str, platform = f"Macintosh; Intel Mac OS X {random.choice(_MAC_OS)}", "macOS"
    else:
        os_str, platform = random.choice(_LNX_OS), "Linux"
    major = random.choice(_CHROME_VER)
    build = random.randint(4000, 9999)
    patch = random.randint(0, 250)
    ua = f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.{build}.{patch} Safari/537.36"
    return {
        "User-Agent": ua,
        "Accept": _CHROME_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-CH-UA": _not_brand(major),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": f'"{platform}"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(["none", "same-origin"]),
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": random.choice(["max-age=0", "no-cache"]),
        "Connection": "keep-alive",
        "Priority": "u=0, i",
    }


def _build_desktop_firefox() -> Dict[str, str]:
    os_type = random.choices(["windows", "mac", "linux"], weights=[60, 25, 15], k=1)[0]
    if os_type == "windows":
        os_str = random.choice(_WIN_OS)
    elif os_type == "mac":
        os_str = f"Macintosh; Intel Mac OS X {random.choice(_MAC_OS).replace('_', '.')}"
    else:
        os_str = random.choice(_LNX_OS)
    major = random.choice(_FIREFOX_VER)
    minor = random.choice([0, 0, 0, 1, 2])
    ver = f"{major}.{minor}" if minor else f"{major}.0"
    ua = f"Mozilla/5.0 ({os_str}; rv:{ver}) Gecko/20100101 Firefox/{ver}"
    return {
        "User-Agent": ua,
        "Accept": _FIREFOX_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(["none", "same-origin"]),
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "DNT": random.choice(["1", "1", "0"]),
        "TE": "trailers",
    }


def _build_desktop_safari() -> Dict[str, str]:
    mac_ver = random.choice(_MAC_OS)
    wk = random.choice(_SAFARI_WK)
    ver = random.choice(_SAFARI_VER)
    os_str = f"Macintosh; Intel Mac OS X {mac_ver}"
    ua = f"Mozilla/5.0 ({os_str}) AppleWebKit/{wk} (KHTML, like Gecko) Version/{ver} Safari/{wk}"
    return {
        "User-Agent": ua,
        "Accept": _SAFARI_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Connection": "keep-alive",
    }


def _build_desktop_edge() -> Dict[str, str]:
    os_str = random.choice(_WIN_OS)
    major = random.choice(_EDGE_VER)
    ch_major = major + random.randint(0, 3)
    build = random.randint(4000, 9999)
    patch = random.randint(0, 250)
    ua = (
        f"Mozilla/5.0 ({os_str}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{ch_major}.0.{build}.{patch} Safari/537.36 Edg/{major}.0.{build}.{patch}"
    )
    return {
        "User-Agent": ua,
        "Accept": _EDGE_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-CH-UA": _not_brand_edge(ch_major),
        "Sec-CH-UA-Mobile": "?0",
        "Sec-CH-UA-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }


def _build_mobile_android_chrome() -> Dict[str, str]:
    android_ver = random.choice(_ANDROID_VER)
    model = random.choice(_ANDROID_MODELS)
    major = random.choice(_CHROME_VER)
    build = random.randint(4000, 9999)
    patch = random.randint(0, 200)
    ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{major}.0.{build}.{patch} Mobile Safari/537.36"
    )
    return {
        "User-Agent": ua,
        "Accept": _CHROME_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-CH-UA": _not_brand(major),
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(["none", "same-origin"]),
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
        "X-Requested-With": "com.android.browser",
    }


def _build_mobile_ios_safari() -> Dict[str, str]:
    ios_ver = random.choice(_IOS_VER)
    iphone = random.choice(_IPHONE_MDL)
    wk = random.choice(_SAFARI_WK)
    ver = random.choice(_SAFARI_VER)
    ios_display = ios_ver.replace("_", " ")
    ua = (
        f"Mozilla/5.0 (iPhone; CPU iPhone OS {ios_ver} like Mac OS X) "
        f"AppleWebKit/{wk} (KHTML, like Gecko) "
        f"Version/{ver} Mobile/15E148 Safari/{wk}"
    )
    return {
        "User-Agent": ua,
        "Accept": _SAFARI_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Connection": "keep-alive",
    }


def _build_ipad_safari() -> Dict[str, str]:
    ios_ver = random.choice(_IOS_VER)
    ipad = random.choice(_IPAD_MDL)
    wk = random.choice(_SAFARI_WK)
    ver = random.choice(_SAFARI_VER)
    ua = (
        f"Mozilla/5.0 (iPad; CPU OS {ios_ver} like Mac OS X) "
        f"AppleWebKit/{wk} (KHTML, like Gecko) "
        f"Version/{ver} Mobile/15E148 Safari/{wk}"
    )
    return {
        "User-Agent": ua,
        "Accept": _SAFARI_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Connection": "keep-alive",
    }


def _build_samsung_internet() -> Dict[str, str]:
    android_ver = random.choice(_ANDROID_VER)
    model = random.choice(_ANDROID_MODELS)
    samsung_ver = random.choice(_SAMSUNG_VER)
    build = random.randint(4000, 9999)
    ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"SamsungBrowser/{samsung_ver} Chrome/120.0.{build}.0 Mobile Safari/537.36"
    )
    return {
        "User-Agent": ua,
        "Accept": _CHROME_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-CH-UA": _not_brand_samsung(samsung_ver),
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }


def _build_mobile_firefox_android() -> Dict[str, str]:
    android_ver = random.choice(_ANDROID_VER)
    major = random.choice(_FIREFOX_VER)
    ver = f"{major}.0"
    ua = (
        f"Mozilla/5.0 (Android {android_ver}; Mobile; rv:{ver}) "
        f"Gecko/{ver} Firefox/{ver}"
    )
    return {
        "User-Agent": ua,
        "Accept": _FIREFOX_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Connection": "keep-alive",
        "DNT": random.choice(["1", "0"]),
    }


def _build_mobile_opera() -> Dict[str, str]:
    android_ver = random.choice(_ANDROID_VER)
    model = random.choice(_ANDROID_MODELS)
    opera_ver = random.choice(_OPERA_VER)
    chrome_major = int(opera_ver) + 14
    build = random.randint(4000, 9999)
    ua = (
        f"Mozilla/5.0 (Linux; Android {android_ver}; {model}) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) "
        f"Chrome/{chrome_major}.0.{build}.0 Mobile Safari/537.36 OPR/{opera_ver}.0.0.0"
    )
    return {
        "User-Agent": ua,
        "Accept": _CHROME_ACCEPT,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-CH-UA": f'"Chromium";v="{chrome_major}", "Opera Mobile";v="{opera_ver}", "Not;A=Brand";v="99"',
        "Sec-CH-UA-Mobile": "?1",
        "Sec-CH-UA-Platform": '"Android"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
        "Connection": "keep-alive",
    }


# Profile weights: real-world browser market share approximation
_PROFILES = [
    (_build_desktop_chrome,         42),
    (_build_mobile_android_chrome,  22),
    (_build_mobile_ios_safari,      14),
    (_build_desktop_edge,            7),
    (_build_desktop_firefox,         6),
    (_build_desktop_safari,          4),
    (_build_samsung_internet,        2),
    (_build_ipad_safari,             1),
    (_build_mobile_firefox_android,  1),
    (_build_mobile_opera,            1),
]
_PROFILE_FUNCS, _PROFILE_WEIGHTS = zip(*_PROFILES)


def get_random_browser_headers() -> Dict[str, str]:
    """Return a complete, humanized, device-consistent browser header set."""
    builder = random.choices(_PROFILE_FUNCS, weights=_PROFILE_WEIGHTS, k=1)[0]
    return builder()


def get_random_user_agent() -> str:
    """Return just the User-Agent string (backwards-compatible)."""
    return get_random_browser_headers()["User-Agent"]
# ---------------------------------------------------------------------------


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

# Status codes that indicate proxy/IP is blocked — auto-rotate to next proxy
_BLOCKED_STATUS_CODES = {403, 407, 429, 503, 521, 522, 523, 524}

# Strings in response body that signal bot detection / captcha / block pages
_BLOCK_BODY_MARKERS = (
    b"captcha", b"CAPTCHA", b"Captcha",
    b"cf-challenge", b"cf_chl", b"__cf_bm",
    b"Access Denied", b"access denied",
    b"Bot Detection", b"bot detection",
    b"Please verify you are a human",
    b"checking your browser", b"Checking Your Browser",
    b"DDoS protection", b"ddos protection",
    b"You have been blocked", b"you have been blocked",
    b"Forbidden", b"403 Forbidden",
    b"rate limit", b"Rate Limit", b"Rate limit",
    b"Too Many Requests",
    b"robots.txt", b"automated access",
)


def _is_blocked_response(status: int, body_sample: bytes) -> bool:
    if status in _BLOCKED_STATUS_CODES:
        return True
    for marker in _BLOCK_BODY_MARKERS:
        if marker in body_sample:
            return True
    return False


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
        raise ValueError("empty proxy string")

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
        "--port", type=int, default=1712, help="Bind port for the local API"
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
        default=200,
        help="Concurrent outbound target fetches handled by the API (default: 200 = ~240+ req/min)",
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
        default=0.1,
        help="Delay between proxy attempts in fetch mode (seconds, default: 0.1)",
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
        "--api-key",
        default="",
        help="Secret key required in X-API-Key header or ?api_key= query param (empty = no auth)",
    )
    parser.add_argument(
        "--cors-origin",
        default="*",
        help="Value for Access-Control-Allow-Origin header (default: *)",
    )
    parser.add_argument(
        "--max-response-mb",
        type=float,
        default=10.0,
        help="Maximum response body size in MB for proxied fetch requests (default: 10)",
    )
    parser.add_argument(
        "--log-requests",
        action="store_true",
        default=False,
        help="Log each API request to stdout",
    )
    parser.add_argument(
        "--tunnel-port",
        type=int,
        default=1909,
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
    parser.add_argument(
        "--tunnel-api-key",
        default="",
        help=(
            "Optional password for standard proxy auth on the tunnel. "
            "Use clients with http://proxy:<key>@host:port."
        ),
    )
    parser.add_argument(
        "--tunnel-auth-user",
        default="proxy",
        help="Username expected for tunnel proxy auth when --tunnel-api-key is set",
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
        # session_id -> last-used proxy URL (LRU, max 10_000 entries)
        self._sticky_sessions: OrderedDict[str, str] = OrderedDict()
        self._sticky_max = 10_000
        self._last_proxy_used: str = ""

    def _update_sticky(self, session_id: str, proxy: str) -> None:
        if session_id in self._sticky_sessions:
            self._sticky_sessions.move_to_end(session_id)
        self._sticky_sessions[session_id] = proxy
        while len(self._sticky_sessions) > self._sticky_max:
            self._sticky_sessions.popitem(last=False)

    def _drop_sticky_proxy(self, proxy: str) -> None:
        stale_sessions = [
            session_id
            for session_id, sticky_proxy in self._sticky_sessions.items()
            if sticky_proxy == proxy
        ]
        for session_id in stale_sessions:
            self._sticky_sessions.pop(session_id, None)

    def _record_runtime_failure(self, record, error: str, probe_url: str) -> None:
        if not self.harvester:
            return
        record.record_failure(
            error=error,
            probe_url=probe_url,
            max_response_time=self.config.max_response_time,
        )
        # Runtime failures are removed from the live rotation immediately.
        # The background verifier can add the proxy back later if it recovers.
        self.harvester.active_proxies.discard(record.proxy)
        self._drop_sticky_proxy(record.proxy)
        self._write_status_file()

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
        connector = aiohttp.TCPConnector(
            limit=self.args.request_concurrency,
            limit_per_host=0,
            ssl=True,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
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
        max_response_bytes: int = 10 * 1024 * 1024,
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

        if (
            len(records_to_try) > 1
            and self._last_proxy_used
            and records_to_try[0].proxy == self._last_proxy_used
        ):
            records_to_try = records_to_try[1:] + records_to_try[:1]

        for index, record in enumerate(records_to_try, start=1):
            proxy_url = parse_proxy_url(record.proxy)

            headers_for_request = sanitize_outbound_headers(headers or {})

            if rotate_ua:
                # Inject full humanized browser fingerprint; caller headers take priority
                browser_hdrs = get_random_browser_headers()
                for hdr_key, hdr_val in browser_hdrs.items():
                    if hdr_key not in headers_for_request:
                        headers_for_request[hdr_key] = hdr_val

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
                    payload_bytes = await response.content.read(max_response_bytes)
                    attempt = {
                        "attempt": index,
                        "proxy": record.proxy,
                        "proxy_url": proxy_url,
                        "score": record.score,
                        "status_code": response.status,
                        "final_url": str(response.url),
                    }
                    # Auto-detect block pages / rate-limiting and skip to next proxy
                    if _is_blocked_response(response.status, payload_bytes[:512]):
                        attempt["error"] = f"blocked: status={response.status}"
                        attempts.append(attempt)
                        self._record_runtime_failure(
                            record,
                            attempt["error"],
                            target_url,
                        )
                        if proxy_delay > 0:
                            await asyncio.sleep(proxy_delay)
                        continue
                    if (
                        expected_status is not None
                        and response.status != expected_status
                    ):
                        attempt["error"] = (
                            f"expected {expected_status}, got {response.status}"
                        )
                        attempts.append(attempt)
                        self._record_runtime_failure(
                            record,
                            attempt["error"],
                            target_url,
                        )
                        if proxy_delay > 0:
                            await asyncio.sleep(proxy_delay)
                        continue

                    record.mark_used()
                    self._last_proxy_used = record.proxy
                    if session_id:
                        self._update_sticky(session_id, record.proxy)
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
                error_name = exc.__class__.__name__
                attempts.append(
                    {
                        "attempt": index,
                        "proxy": record.proxy,
                        "proxy_url": proxy_url,
                        "score": record.score,
                        "error": error_name,
                    }
                )
                self._record_runtime_failure(record, error_name, target_url)

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
        auth_user: str = "proxy",
        auth_key: str = "",
    ):
        self.service = service
        self.host = host
        self.port = port
        self.max_attempts = max_attempts
        self.connect_timeout = connect_timeout
        self.relay_timeout = relay_timeout
        self.rotate_ua = rotate_ua
        self.auth_user = auth_user
        self.auth_key = auth_key
        self._server: Optional[asyncio.Server] = None
        self._stats: Dict[str, int] = {
            "total_requests": 0,
            "connect_requests": 0,
            "http_requests": 0,
            "successful": 0,
            "failed": 0,
        }
        self._last_proxy_used: str = ""

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
        if len(pool) > 1 and pool[0].proxy == self._last_proxy_used:
            pool = pool[1:] + pool[:1]
        return pool[: self.max_attempts]

    # ---- client entry point ------------------------------------------------

    async def _read_request_headers(
        self, client_reader: asyncio.StreamReader
    ) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(
                client_reader.readline(), timeout=self.connect_timeout,
            )
            if line in (b"\r\n", b"\n", b""):
                break
            decoded = line.decode("latin-1", errors="replace").strip()
            if ":" in decoded:
                key, value = decoded.split(":", 1)
                headers[key.strip()] = value.strip()
        return headers

    def _is_authorized(self, headers: Dict[str, str]) -> bool:
        if not self.auth_key:
            return True

        auth_value = ""
        for key, value in headers.items():
            if key.lower() == "proxy-authorization":
                auth_value = value
                break
        if not auth_value.lower().startswith("basic "):
            return False

        try:
            decoded = base64.b64decode(auth_value.split(None, 1)[1]).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            return False

        expected = f"{self.auth_user}:{self.auth_key}"
        return hmac.compare_digest(decoded, expected)

    async def _send_proxy_auth_required(
        self, client_writer: asyncio.StreamWriter
    ) -> None:
        client_writer.write(
            b'HTTP/1.1 407 Proxy Authentication Required\r\n'
            b'Proxy-Authenticate: Basic realm="Proxy Generator"\r\n'
            b'Content-Length: 0\r\n\r\n'
        )
        await client_writer.drain()

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
            headers = await self._read_request_headers(client_reader)

            if not self._is_authorized(headers):
                await self._send_proxy_auth_required(client_writer)
                self._stats["failed"] += 1
                return

            if decoded.upper().startswith("CONNECT "):
                self._stats["connect_requests"] += 1
                await self._handle_connect(
                    decoded, headers, client_reader, client_writer
                )
            else:
                self._stats["http_requests"] += 1
                await self._handle_plain_http(
                    decoded, headers, client_reader, client_writer,
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
        headers: Dict[str, str],
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

        proxies = self._pick_proxies()
        if not proxies:
            client_writer.write(b"HTTP/1.1 502 No Proxies Available\r\n\r\n")
            await client_writer.drain()
            self._stats["failed"] += 1
            return

        for record in proxies:
            try:
                proxy_url = parse_proxy_url(record.proxy)
            except ValueError:
                self.service._record_runtime_failure(
                    record,
                    "invalid_proxy_url",
                    f"{target_host}:{target_port}",
                )
                continue
            try:
                if proxy_url.startswith("socks"):
                    if not _SOCKS_TUNNEL_OK:
                        continue
                    ok = await self._tunnel_via_socks_proxy(
                        proxy_url, target_host, target_port,
                        client_reader, client_writer,
                    )
                else:
                    ok = await self._tunnel_via_http_proxy(
                        proxy_url, target_host, target_port,
                        client_reader, client_writer,
                    )
                if ok:
                    record.mark_used()
                    self._last_proxy_used = record.proxy
                    self._stats["successful"] += 1
                    return
                self.service._record_runtime_failure(
                    record,
                    "connect_tunnel_failed",
                    f"{target_host}:{target_port}",
                )
            except Exception:
                self.service._record_runtime_failure(
                    record,
                    "connect_tunnel_exception",
                    f"{target_host}:{target_port}",
                )
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
            p_port = 80

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

    async def _tunnel_via_socks_proxy(
        self,
        proxy_url: str,
        target_host: str,
        target_port: int,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> bool:
        """Open a CONNECT tunnel through a SOCKS4/5 proxy using python-socks."""
        try:
            proxy = _SocksProxy.from_url(proxy_url)
            sock = await asyncio.wait_for(
                proxy.connect(dest_host=target_host, dest_port=target_port),
                timeout=self.connect_timeout,
            )
            up_reader, up_writer = await asyncio.open_connection(sock=sock)
            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
            await self._relay(client_reader, client_writer, up_reader, up_writer)
            return True
        except Exception:
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
        request_headers: Dict[str, str],
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

        content_length = 0
        headers: Dict[str, str] = {}
        for key, value in request_headers.items():
            if key.lower() == "content-length":
                try:
                    content_length = int(value)
                except ValueError:
                    content_length = 0
            if key.lower() not in HOP_BY_HOP_HEADERS:
                headers[key] = value

        body: Optional[bytes] = None
        if content_length > 0:
            body = await asyncio.wait_for(
                client_reader.readexactly(content_length),
                timeout=self.connect_timeout,
            )

        if self.rotate_ua:
            browser_hdrs = get_random_browser_headers()
            for hdr_key, hdr_val in browser_hdrs.items():
                if hdr_key not in headers:
                    headers[hdr_key] = hdr_val

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
        "headers": sanitize_outbound_headers(dict(request.headers)),
        "body": raw_body or None,
    }


def json_error(message: str, status: int = 400, **extra: Any) -> web.Response:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    return web.json_response(payload, status=status)


@web.middleware
async def cors_middleware(request: web.Request, handler) -> web.Response:
    allowed_origin = request.app.get("cors_origin", "*")
    if request.method == "OPTIONS":
        return web.Response(
            status=204,
            headers={
                "Access-Control-Allow-Origin": allowed_origin,
                "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
                "Access-Control-Max-Age": "86400",
            },
        )
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = allowed_origin
    return response


@web.middleware
async def api_key_middleware(request: web.Request, handler) -> web.Response:
    api_key = request.app.get("api_key")
    if not api_key:
        return await handler(request)
    # Health check always passes without auth
    if request.path in ("/health",):
        return await handler(request)
    provided = (
        request.headers.get("X-API-Key")
        or request.query.get("api_key")
    )
    if provided != api_key:
        return json_error("unauthorized: valid X-API-Key header or ?api_key= required", status=401)
    return await handler(request)


@web.middleware
async def request_logging_middleware(request: web.Request, handler) -> web.Response:
    response = await handler(request)
    logger.info("%s %s -> %s", request.method, request.path, response.status)
    return response


async def handle_status(request: web.Request) -> web.Response:
    service: ProxyAPIService = request.app["service"]
    include_proxies = request.query.get("include_proxies", "false").lower() == "true"
    limit = int(request.query.get("limit", "20"))
    return web.json_response(
        service.status_payload(include_proxies=include_proxies, limit=limit)
    )


async def handle_reload(request: web.Request) -> web.Response:
    """POST /reload — force immediate proxy pool refresh."""
    service: ProxyAPIService = request.app["service"]
    summary = await service.refresh_once(force_collect=True, force_verify=True)
    return web.json_response({
        "ok": True,
        "message": "pool refresh triggered",
        "active_proxies": summary.get("active_proxies", 0),
        "added": summary.get("added_active", 0),
        "removed": summary.get("removed_active", 0),
    })


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

    middlewares = [cors_middleware, api_key_middleware]
    if getattr(args, "log_requests", False):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
        middlewares.append(request_logging_middleware)

    app = web.Application(
        client_max_size=20 * 1024 * 1024,
        middlewares=middlewares,
    )
    app["service"] = service
    app["api_key"] = getattr(args, "api_key", "") or None
    app["cors_origin"] = getattr(args, "cors_origin", "*")

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
    app.router.add_post("/reload", handle_reload)
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
            auth_user=getattr(args, "tunnel_auth_user", "proxy"),
            auth_key=getattr(args, "tunnel_api_key", ""),
        )
        app["tunnel"] = tunnel

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=args.host, port=args.port)
    access_urls = build_access_urls(args.host, args.port, args.public_base_url)

    api_key = getattr(args, "api_key", "") or None
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
    if api_key:
        print(f"\n  Auth: X-API-Key: {api_key}  (or ?api_key={api_key})")
    else:
        print("\n  Auth: DISABLED (use --api-key to enable)")
    print("\nAPI Endpoints:")
    print(f"  GET  {preferred_url}/status")
    print(f"  GET  {preferred_url}/stats                  -- pool breakdown by protocol/country/anonymity")
    print(f"  GET  {preferred_url}/proxies                -- list proxies (?protocol= &country= &anonymity= &min_score=)")
    print(f"  GET  {preferred_url}/next                   -- round-robin next proxy (?protocol= &country= &anonymity=)")
    print(f"  GET  {preferred_url}/random                 -- random proxy from pool (?protocol= &country= &anonymity=)")
    print(f"  GET  {preferred_url}/proxy?url=https://example.com  -- fetch URL through rotating proxy")
    print(f"  POST {preferred_url}/fetch                  -- JSON body: {{url, method, headers, session_id, ...}}")
    print(f"  POST {preferred_url}/reload                 -- force immediate pool refresh")
    print(f"  GET  {preferred_url}/tunnel-status")
    if tunnel_port > 0:
        tunnel_auth_key = getattr(args, "tunnel_api_key", "") or ""
        auth_user = getattr(args, "tunnel_auth_user", "proxy")
        if tunnel_auth_key:
            print(
                f"\nProxy Tunnel: http://{auth_user}:<tunnel-api-key>@{tunnel_host}:{tunnel_port}"
            )
        else:
            print(f"\nProxy Tunnel: http://{tunnel_host}:{tunnel_port}")

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
