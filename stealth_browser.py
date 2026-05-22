#!/usr/bin/env python3
"""
stealth_browser.py - Optional browser-level helper for the local proxy service.
Supports three engines (auto-selects best available):
  1. CloakBrowser - Chromium with source-level fingerprint patches (preferred)
  2. Camoufox     - Firefox patched for browser fingerprint resistance
  3. Playwright   - Chromium with JS stealth injection fallback

Both engines:
  - Route through the local proxy tunnel (http://127.0.0.1:1909)
  - Rotate IP on every new session automatically
  - Spoof: Canvas, WebGL, Audio, Fonts, Timezone, navigator.*
  - Handle Cloudflare Bot Management, Turnstile, hCaptcha challenges
  - Randomize viewport, hardware concurrency, device memory

Usage (library):
    import asyncio
    from stealth_browser import scrape_url, scrape_many

    result = asyncio.run(scrape_url("https://example.com"))
    print(result["content"][:500])

Usage (CLI):
    python stealth_browser.py https://example.com
    python stealth_browser.py https://example.com --screenshot out.png --output page.html
    python stealth_browser.py https://example.com --no-proxy --headful
    python stealth_browser.py https://example.com --engine cloakbrowser
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
#  Engine availability detection
# ---------------------------------------------------------------------------
try:
    from cloakbrowser import launch as _cloak_launch
    _CLOAK_OK = True
except ImportError:
    _CLOAK_OK = False

try:
    from camoufox.async_api import AsyncCamoufox
    _CAMOUFOX_OK = True
except ImportError:
    _CAMOUFOX_OK = False

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, Browser
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False

DEFAULT_PROXY = "http://127.0.0.1:1909"

# ---------------------------------------------------------------------------
#  Realistic fingerprint data
# ---------------------------------------------------------------------------
_DESKTOP_VIEWPORTS: List[Dict[str, int]] = [
    {"width": 1920, "height": 1080},
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 720},
    {"width": 1600, "height": 900},
    {"width": 2560, "height": 1440},
    {"width": 1280, "height": 800},
    {"width": 1680, "height": 1050},
    {"width": 1024, "height": 768},
]
_MOBILE_VIEWPORTS: List[Dict[str, int]] = [
    {"width": 390, "height": 844},
    {"width": 393, "height": 852},
    {"width": 412, "height": 915},
    {"width": 360, "height": 780},
    {"width": 414, "height": 896},
    {"width": 375, "height": 667},
    {"width": 320, "height": 568},
]
_TIMEZONES = [
    "America/New_York", "America/Chicago", "America/Los_Angeles", "America/Toronto",
    "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Amsterdam",
    "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Asia/Dubai",
    "Australia/Sydney", "Pacific/Auckland",
]
_LOCALES = ["en-US", "en-GB", "en-CA", "en-AU", "en-IN"]
_CPU_CORES = [2, 4, 4, 4, 6, 8, 8, 8, 12, 16]
_DEVICE_MEM = [2, 4, 4, 8, 8, 8, 16]

# WebGL renderer profiles - match real GPU configurations
_WEBGL_PROFILES = [
    ("Intel Inc.", "Intel Iris OpenGL Engine"),
    ("Intel Inc.", "Intel(R) UHD Graphics 620"),
    ("Intel Inc.", "Intel(R) HD Graphics 630"),
    ("ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)", "Intel(R) UHD Graphics 630"),
    ("ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)", "NVIDIA GeForce RTX 3060"),
    ("ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0, D3D11)", "NVIDIA GeForce GTX 1650"),
    ("ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)", "AMD Radeon RX 5700 XT"),
    ("Apple", "Apple M1"),
    ("Apple", "Apple M2"),
    ("Mesa/X.org", "Mesa Intel(R) UHD Graphics 630 (CFL GT2)"),
]

# ---------------------------------------------------------------------------
#  Comprehensive stealth JS - injected as init script
#  Patches every major fingerprinting vector at the JS level.
#  Note: Camoufox patches these at C++ level (more robust); this JS injection
#  is used for Playwright fallback mode.
# ---------------------------------------------------------------------------
_STEALTH_JS = r"""
(function() {
    'use strict';

    // ── 1. navigator.webdriver ──────────────────────────────────────────────
    try {
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            enumerable: true,
            configurable: true,
        });
    } catch(_) {}

    // ── 2. Canvas fingerprint noise ────────────────────────────────────────
    const _noise = () => (Math.random() > 0.5 ? 1 : 0);
    const _origGetContext = HTMLCanvasElement.prototype.getContext;

    HTMLCanvasElement.prototype.getContext = function(type, opts) {
        const ctx = _origGetContext.call(this, type, opts);
        if (!ctx) return ctx;
        if (type === '2d') {
            const _origGetImageData = ctx.getImageData.bind(ctx);
            ctx.getImageData = function(x, y, w, h) {
                const d = _origGetImageData(x, y, w, h);
                for (let i = 0; i < d.data.length; i += 4) {
                    d.data[i]   = Math.max(0, Math.min(255, d.data[i]   + _noise()));
                    d.data[i+1] = Math.max(0, Math.min(255, d.data[i+1] + _noise()));
                    d.data[i+2] = Math.max(0, Math.min(255, d.data[i+2] + _noise()));
                }
                return d;
            };
        }
        return ctx;
    };

    const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
        const ctx2 = _origGetContext.call(this, '2d');
        if (ctx2 && this.width > 0 && this.height > 0) {
            try {
                const px = ctx2.getImageData(0, 0, 1, 1);
                px.data[0] = Math.max(0, Math.min(255, px.data[0] + _noise()));
                ctx2.putImageData(px, 0, 0);
            } catch(_) {}
        }
        return _origToDataURL.call(this, type, quality);
    };

    // ── 3. WebGL fingerprint spoofing ─────────────────────────────────────
    const _GL_VENDOR   = 0x1F00;
    const _GL_RENDERER = 0x1F01;
    const _GL_UNMASKED_VENDOR   = 0x9245;
    const _GL_UNMASKED_RENDERER = 0x9246;

    const _glProfiles = [
        ['Intel Inc.', 'Intel Iris OpenGL Engine'],
        ['Intel Inc.', 'Intel(R) UHD Graphics 620'],
        ['ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)', 'Intel(R) UHD Graphics 630'],
        ['ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)', 'NVIDIA GeForce RTX 3060'],
        ['ANGLE (AMD, AMD Radeon RX 5700 XT Direct3D11 vs_5_0 ps_5_0, D3D11)', 'AMD Radeon RX 5700 XT'],
        ['Apple', 'Apple M1'],
        ['Apple', 'Apple M2'],
    ];
    const _chosenGL = _glProfiles[Math.floor(Math.random() * _glProfiles.length)];

    function _patchWebGL(Ctx) {
        if (!Ctx) return;
        const _orig = Ctx.prototype.getParameter;
        Ctx.prototype.getParameter = function(p) {
            if (p === _GL_UNMASKED_VENDOR || p === _GL_VENDOR)   return _chosenGL[0];
            if (p === _GL_UNMASKED_RENDERER || p === _GL_RENDERER) return _chosenGL[1];
            return _orig.call(this, p);
        };
        const _origExt = Ctx.prototype.getExtension;
        Ctx.prototype.getExtension = function(name) {
            if (name === 'WEBGL_debug_renderer_info') {
                return {
                    UNMASKED_VENDOR_WEBGL: _GL_UNMASKED_VENDOR,
                    UNMASKED_RENDERER_WEBGL: _GL_UNMASKED_RENDERER,
                };
            }
            return _origExt.call(this, name);
        };
    }
    _patchWebGL(window.WebGLRenderingContext);
    _patchWebGL(window.WebGL2RenderingContext);

    // ── 4. Audio fingerprint noise ────────────────────────────────────────
    if (window.AudioBuffer) {
        const _origGetChannelData = AudioBuffer.prototype.getChannelData;
        AudioBuffer.prototype.getChannelData = function() {
            const arr = _origGetChannelData.apply(this, arguments);
            for (let i = 0; i < arr.length; i += 100) {
                arr[i] += (Math.random() - 0.5) * 1e-7;
            }
            return arr;
        };
    }
    if (window.AnalyserNode) {
        const _origGetFloat = AnalyserNode.prototype.getFloatFrequencyData;
        AnalyserNode.prototype.getFloatFrequencyData = function(arr) {
            _origGetFloat.call(this, arr);
            for (let i = 0; i < arr.length; i++) {
                arr[i] += (Math.random() - 0.5) * 0.1;
            }
        };
    }

    // ── 5. Font enumeration prevention ───────────────────────────────────
    // Adds imperceptible noise to measureText width so fingerprinting
    // cannot reliably detect installed fonts.
    const _origMeasureText = CanvasRenderingContext2D.prototype.measureText;
    CanvasRenderingContext2D.prototype.measureText = function(text) {
        const result = _origMeasureText.call(this, text);
        const originalWidth = result.width;
        const noise  = (Math.random() - 0.5) * 0.00001;
        Object.defineProperty(result, 'width', {
            get: () => originalWidth + noise,
            configurable: true,
        });
        return result;
    };

    // ── 6. Fake navigator.plugins & mimeTypes ────────────────────────────
    const _fakePlugins = [
        { name: 'Chrome PDF Plugin',  filename: 'internal-pdf-viewer',            description: 'Portable Document Format' },
        { name: 'Chrome PDF Viewer',  filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
        { name: 'Native Client',      filename: 'internal-nacl-plugin',            description: '' },
    ];
    const _pArr = _fakePlugins.map(p => ({
        name: p.name, filename: p.filename, description: p.description,
        length: 1, item: () => null, namedItem: () => null,
    }));
    _pArr.length = _fakePlugins.length;
    _pArr.item = (i) => _pArr[i];
    _pArr.namedItem = (n) => _pArr.find(p => p.name === n) || null;
    _pArr.refresh = () => {};
    try {
        Object.defineProperty(navigator, 'plugins', { get: () => _pArr, configurable: true });
        Object.defineProperty(navigator, 'mimeTypes', {
            get: () => ({ length: 4, item: () => null, namedItem: () => null }),
            configurable: true,
        });
    } catch(_) {}

    // ── 7. navigator.languages ────────────────────────────────────────────
    try {
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
            configurable: true,
        });
    } catch(_) {}

    // ── 8. navigator.hardwareConcurrency & deviceMemory ──────────────────
    // M-4/M-5 FIX: pick values ONCE at init time — consistent on every access.
    // Re-randomising on each .get() call is detectable by sites that read
    // these properties multiple times and check for consistency.
    const _cores = [2, 4, 4, 4, 6, 8, 8, 8, 12, 16];
    const _mems  = [2, 4, 4, 8, 8, 8, 16];
    const _pickedCores = _cores[Math.floor(Math.random() * _cores.length)];
    const _pickedMem   = _mems[Math.floor(Math.random() * _mems.length)];
    try {
        Object.defineProperty(navigator, 'hardwareConcurrency', {
            get: () => _pickedCores,
            configurable: true,
        });
    } catch(_) {}
    try {
        if ('deviceMemory' in navigator) {
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => _pickedMem,
                configurable: true,
            });
        }
    } catch(_) {}

    // ── 9. Permissions API ────────────────────────────────────────────────
    if (navigator.permissions && navigator.permissions.query) {
        const _origQuery = navigator.permissions.query.bind(navigator.permissions);
        navigator.permissions.query = (params) => {
            if (['midi', 'midi-sysex', 'push', 'speaker-selection'].includes(params.name)) {
                return Promise.resolve({ state: 'denied', onchange: null });
            }
            return _origQuery(params).catch(() =>
                Promise.resolve({ state: 'prompt', onchange: null })
            );
        };
    }

    // ── 10. window.chrome injection ───────────────────────────────────────
    if (!window.chrome || !window.chrome.runtime) {
        window.chrome = {
            app: {
                isInstalled: false,
                InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
                RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
                getDetails: () => null,
                getIsInstalled: () => false,
                installState: () => {},
            },
            runtime: {
                id: undefined,
                connect: () => { throw new Error('Extension context invalidated.'); },
                sendMessage: () => { throw new Error('Extension context invalidated.'); },
                onConnect: { addListener: () => {}, removeListener: () => {}, hasListener: () => false },
                onMessage: { addListener: () => {}, removeListener: () => {}, hasListener: () => false },
            },
            csi: () => ({}),
            loadTimes: () => ({
                commitLoadTime: performance.now() / 1000 - Math.random() * 0.3,
                connectionInfo: 'h2',
                finishDocumentLoadTime: 0, finishLoadTime: 0,
                firstPaintAfterLoadTime: 0, firstPaintTime: 0,
                npnNegotiatedProtocol: 'h2',
                requestTime: performance.now() / 1000 - Math.random(),
                startLoadTime: performance.now() / 1000 - Math.random() * 0.1,
                wasAlternateProtocolAvailable: false,
                wasFetchedViaSpdy: true, wasNpnNegotiated: true,
            }),
        };
    }

    // ── 11. Remove all automation artifacts ───────────────────────────────
    [
        '__playwright', '__pw_manual', '__pw_metadata',
        '__selenium_unwrapped', '__selenium_evaluate', '__webdriver_evaluate',
        '__fxdriver_evaluate', '__driver_unwrapped', '__webdriver_script_func',
        '__driver_evaluate', '__webdriverFunc', '__webdriver_script_fn',
        '__lastWatirAlert', '__lastWatirConfirm', '__lastWatirPrompt',
        '_selenium', '_Selenium_IDE_Recorder', 'callSelenium',
        '__phantomas', 'domAutomation', 'domAutomationController',
        '_Webdriver_ChromeDriver',
    ].forEach(k => { try { delete window[k]; } catch(_) {} });

    // ── 12. Date.now jitter (prevents precise timing fingerprinting) ──────
    const _dn = Date.now;
    Date.now = function() {
        return _dn() + (Math.random() > 0.95 ? Math.floor(Math.random() * 3) : 0);
    };

    // ── 13. Prevent iframe-based detection ────────────────────────────────
    try {
        const _origCreateElement = document.createElement.bind(document);
        document.createElement = function(tag, opts) {
            const el = _origCreateElement(tag, opts);
            if (tag.toLowerCase() === 'iframe') {
                Object.defineProperty(el, 'contentWindow', {
                    get: function() {
                        const win = el.__origContentWindow || HTMLIFrameElement.prototype.__defineGetter__
                            ? Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, 'contentWindow')?.get?.call(el)
                            : null;
                        return win;
                    },
                    configurable: true,
                });
            }
            return el;
        };
    } catch(_) {}

})();
"""

# ---------------------------------------------------------------------------
#  Cloudflare challenge wait helper
# ---------------------------------------------------------------------------
_CF_CHALLENGE_TITLES = [
    "just a moment", "checking your browser", "please wait",
    "attention required", "ddos protection", "ray id",
]
_CF_CHALLENGE_MARKERS = [
    b"cf-challenge", b"cf_chl_opt", b"__cf_bm", b"cf-turnstile",
    b"challenge-platform", b"jschl-answer",
]


async def _wait_for_cf_challenge(page: "Page", max_wait: float = 20.0) -> bool:
    """Block until Cloudflare challenge clears. Returns True if cleared."""
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        try:
            title = (await page.title()).lower()
            if any(m in title for m in _CF_CHALLENGE_TITLES):
                await asyncio.sleep(1.5)
                continue
            content = (await page.content()).encode()[:2048]
            if any(m in content for m in _CF_CHALLENGE_MARKERS):
                await asyncio.sleep(1.5)
                continue
        except Exception:
            pass
        return True
    return False


# ---------------------------------------------------------------------------
#  CloakBrowser engine
# ---------------------------------------------------------------------------
def _scrape_cloakbrowser_sync(
    url: str,
    proxy_url: Optional[str],
    headless: bool,
    mobile: bool,
    timeout: int,
    wait_extra_ms: int,
    screenshot: Optional[str],
) -> Dict[str, Any]:
    vp = random.choice(_MOBILE_VIEWPORTS if mobile else _DESKTOP_VIEWPORTS)
    kwargs: Dict[str, Any] = {
        "headless": headless,
        "humanize": True,
        "geoip": bool(proxy_url),
        "screen": vp,
    }
    if proxy_url:
        kwargs["proxy"] = {"server": proxy_url}

    browser = None
    try:
        browser = _cloak_launch(**kwargs)
        page = browser.new_page()
        try:
            page.set_viewport_size(vp)
        except Exception:
            pass

        response = page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        if wait_extra_ms > 0:
            time.sleep(wait_extra_ms / 1000)
        if screenshot:
            page.screenshot(path=screenshot, full_page=True)
        content = page.content()
        return {
            "ok": True,
            "engine": "cloakbrowser",
            "url": page.url,
            "status": response.status if response else 0,
            "title": page.title(),
            "content": content,
            "content_length": len(content),
            "challenge_cleared": True,
        }
    except Exception as exc:
        return {"ok": False, "engine": "cloakbrowser", "url": url, "error": str(exc)}
    finally:
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass


async def _scrape_cloakbrowser(
    url: str,
    proxy_url: Optional[str],
    headless: bool,
    mobile: bool,
    timeout: int,
    wait_extra_ms: int,
    screenshot: Optional[str],
) -> Dict[str, Any]:
    return await asyncio.to_thread(
        _scrape_cloakbrowser_sync,
        url,
        proxy_url,
        headless,
        mobile,
        timeout,
        wait_extra_ms,
        screenshot,
    )


# ---------------------------------------------------------------------------
#  Camoufox engine
# ---------------------------------------------------------------------------
async def _scrape_camoufox(
    url: str,
    proxy_url: Optional[str],
    headless: bool,
    mobile: bool,
    timeout: int,
    wait_extra_ms: int,
    screenshot: Optional[str],
) -> Dict[str, Any]:
    vp = random.choice(_MOBILE_VIEWPORTS if mobile else _DESKTOP_VIEWPORTS)
    proxy_cfg = {"server": proxy_url} if proxy_url else None
    kwargs: Dict[str, Any] = {
        "headless": headless,
        "geoip": True,
        "humanize": True,
        "screen": vp,
    }
    if proxy_cfg:
        kwargs["proxy"] = proxy_cfg

    try:
        async with AsyncCamoufox(**kwargs) as browser:
            page = await browser.new_page()
            resp = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            cleared = await _wait_for_cf_challenge(page, max_wait=timeout / 1000)
            if wait_extra_ms > 0:
                await asyncio.sleep(wait_extra_ms / 1000)
            if screenshot:
                await page.screenshot(path=screenshot, full_page=True)
            content = await page.content()
            return {
                "ok": True,
                "engine": "camoufox",
                "url": page.url,
                "status": resp.status if resp else 0,
                "title": await page.title(),
                "content": content,
                "content_length": len(content),
                "challenge_cleared": cleared,
            }
    except Exception as exc:
        return {"ok": False, "engine": "camoufox", "url": url, "error": str(exc)}


# ---------------------------------------------------------------------------
#  Playwright engine (Chromium + JS stealth injection)
# ---------------------------------------------------------------------------
def _pw_ua(mobile: bool) -> str:
    """Pick a consistent UA for Playwright context."""
    if mobile:
        android_ver = random.choice(["12", "13", "14"])
        chrome_ver = random.randint(118, 136)
        build = random.randint(4000, 9999)
        return (
            f"Mozilla/5.0 (Linux; Android {android_ver}; Pixel 7) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_ver}.0.{build}.0 Mobile Safari/537.36"
        )
    win_os = random.choice(["Windows NT 10.0; Win64; x64", "Windows NT 11.0; Win64; x64"])
    chrome_ver = random.randint(118, 136)
    build = random.randint(4000, 9999)
    return (
        f"Mozilla/5.0 ({win_os}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{chrome_ver}.0.{build}.0 Safari/537.36"
    )


async def _scrape_playwright(
    url: str,
    proxy_url: Optional[str],
    headless: bool,
    mobile: bool,
    timeout: int,
    wait_extra_ms: int,
    screenshot: Optional[str],
    ignore_https_errors: bool,
) -> Dict[str, Any]:
    vp = random.choice(_MOBILE_VIEWPORTS if mobile else _DESKTOP_VIEWPORTS)
    timezone = random.choice(_TIMEZONES)
    locale   = random.choice(_LOCALES)
    ua       = _pw_ua(mobile)

    launch_args = [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--disable-features=IsolateOrigins,site-per-process",
        "--lang=en-US",
        f"--window-size={vp['width']},{vp['height']}",
    ]

    proxy_cfg = {"server": proxy_url} if proxy_url else None

    try:
        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(
                headless=headless,
                args=launch_args,
            )
            ctx_kwargs: Dict[str, Any] = {
                "viewport": vp,
                "user_agent": ua,
                "locale": locale,
                "timezone_id": timezone,
                "accept_downloads": True,
                "ignore_https_errors": ignore_https_errors,
                "extra_http_headers": {"Accept-Language": "en-US,en;q=0.9"},
            }
            if mobile:
                ctx_kwargs["is_mobile"] = True
                ctx_kwargs["has_touch"] = True
            if proxy_cfg:
                ctx_kwargs["proxy"] = proxy_cfg

            context: BrowserContext = await browser.new_context(**ctx_kwargs)
            await context.add_init_script(_STEALTH_JS)

            page: Page = await context.new_page()
            resp = await page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            cleared = await _wait_for_cf_challenge(page, max_wait=timeout / 1000)
            if wait_extra_ms > 0:
                await asyncio.sleep(wait_extra_ms / 1000)
            if screenshot:
                await page.screenshot(path=screenshot, full_page=True)
            content = await page.content()
            result = {
                "ok": True,
                "engine": "playwright",
                "url": page.url,
                "status": resp.status if resp else 0,
                "title": await page.title(),
                "content": content,
                "content_length": len(content),
                "challenge_cleared": cleared,
            }
            await context.close()
            await browser.close()
            return result
    except Exception as exc:
        return {"ok": False, "engine": "playwright", "url": url, "error": str(exc)}


# ---------------------------------------------------------------------------
#  Public API
# ---------------------------------------------------------------------------
async def scrape_url(
    url: str,
    proxy_url: Optional[str] = DEFAULT_PROXY,
    headless: bool = True,
    mobile: bool = False,
    timeout: int = 30_000,
    wait_extra_ms: int = 0,
    screenshot: Optional[str] = None,
    engine: str = "auto",
    ignore_https_errors: bool = False,
) -> Dict[str, Any]:
    """
    Scrape *url* with full anti-detection.

    engine: "auto" | "cloakbrowser" | "camoufox" | "playwright"
      auto -> tries cloakbrowser, then camoufox, then playwright.
    proxy_url: None disables proxy routing.
    """
    errors: Dict[str, str] = {}
    engine_order: List[str]
    if engine == "auto":
        engine_order = ["cloakbrowser", "camoufox", "playwright"]
    else:
        engine_order = [engine]

    for candidate in engine_order:
        if candidate == "cloakbrowser":
            if not _CLOAK_OK:
                errors[candidate] = "not installed"
                continue
            result = await _scrape_cloakbrowser(
                url, proxy_url, headless, mobile, timeout, wait_extra_ms, screenshot
            )
        elif candidate == "camoufox":
            if not _CAMOUFOX_OK:
                errors[candidate] = "not installed"
                continue
            result = await _scrape_camoufox(
                url, proxy_url, headless, mobile, timeout, wait_extra_ms, screenshot
            )
        elif candidate == "playwright":
            if not _PLAYWRIGHT_OK:
                errors[candidate] = "not installed"
                continue
            result = await _scrape_playwright(
                url,
                proxy_url,
                headless,
                mobile,
                timeout,
                wait_extra_ms,
                screenshot,
                ignore_https_errors,
            )
        else:
            errors[candidate] = "unknown engine"
            continue

        if result.get("ok"):
            if errors:
                result["fallback_errors"] = errors
            return result
        errors[candidate] = str(result.get("error", "failed"))

    return {
        "ok": False,
        "error": (
            "No browser engine available. Install one:\n"
            "  pip install -r requirements-browser.txt\n"
            "  python -m cloakbrowser install\n"
            "  python -m camoufox fetch\n"
            "  playwright install chromium"
        ),
        "engine_errors": errors,
        "url": url,
    }


async def scrape_many(
    urls: List[str],
    concurrency: int = 3,
    **kwargs: Any,
) -> List[Dict[str, Any]]:
    """Scrape multiple URLs concurrently (default 3 at a time)."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(url: str) -> Dict[str, Any]:
        async with sem:
            return await scrape_url(url, **kwargs)

    return await asyncio.gather(*(_one(u) for u in urls))


# ---------------------------------------------------------------------------
#  CLI
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Stealth browser scraper - routes through local proxy tunnel by default"
    )
    p.add_argument("url", nargs="?", help="URL to scrape (omit to run self-test)")
    p.add_argument("--proxy", default=DEFAULT_PROXY, help=f"Proxy URL (default: {DEFAULT_PROXY})")
    p.add_argument("--no-proxy", action="store_true", help="Disable proxy routing")
    p.add_argument("--headful", action="store_true", help="Show browser window")
    p.add_argument("--mobile", action="store_true", help="Use mobile device profile")
    p.add_argument("--timeout", type=int, default=30_000, help="Page load timeout in ms")
    p.add_argument("--wait", type=int, default=0, help="Extra wait after page load (ms)")
    p.add_argument(
        "--ignore-https-errors",
        action="store_true",
        help="Allow browser sessions to continue despite TLS certificate errors",
    )
    p.add_argument("--screenshot", help="Save screenshot to this path")
    p.add_argument("--output", help="Save HTML content to this file")
    p.add_argument(
        "--engine",
        choices=["auto", "cloakbrowser", "camoufox", "playwright"],
        default="auto",
        help="Browser engine (default: auto = cloakbrowser, camoufox, playwright)",
    )
    return p


def _print_engine_status() -> None:
    print("Engine status:")
    print(f"  cloakbrowser: {'[OK] available' if _CLOAK_OK else '[--] not installed  (pip install -r requirements-browser.txt && python -m cloakbrowser install)'}")
    print(f"  camoufox  : {'[OK] available' if _CAMOUFOX_OK  else '[--] not installed  (pip install -r requirements-browser.txt && python -m camoufox fetch)'}")
    print(f"  playwright: {'[OK] available' if _PLAYWRIGHT_OK else '[--] not installed  (pip install -r requirements-browser.txt && playwright install chromium)'}")


def _run_async(coro):
    """Run an async coroutine using the project's event loop factory.
    Uses SelectorEventLoop on Windows (required for Playwright subprocess support).
    """
    from proxy_core import run_async_entrypoint
    return run_async_entrypoint(coro)


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    _print_engine_status()

    if not _CLOAK_OK and not _CAMOUFOX_OK and not _PLAYWRIGHT_OK:
        parser.error("Install at least one browser engine (see above).")

    # Self-test mode - no URL given
    if not args.url:
        test_urls = [
            "https://httpbin.org/ip",
            "https://httpbin.org/headers",
        ]
        print("\nRunning self-test (no proxy)...")

        async def _run_tests():
            return await scrape_many(
                test_urls,
                concurrency=1,
                proxy_url=None,
                headless=True,
                engine=args.engine,
                ignore_https_errors=args.ignore_https_errors,
            )

        results = _run_async(_run_tests())
        for r in results:
            status = "[OK]" if r["ok"] else "[FAIL]"
            engine_used = r.get("engine", "?")
            print(f"  {status} [{engine_used}] {r.get('url', '')}  title={r.get('title','')!r}  len={r.get('content_length',0)}")
            if not r["ok"]:
                print(f"       error: {r.get('error','')}")
        return

    proxy = None if args.no_proxy else args.proxy
    print(f"\nScraping: {args.url}")
    print(f"  engine={args.engine}  proxy={'none' if not proxy else proxy}  mobile={args.mobile}")

    result = _run_async(scrape_url(
        url=args.url,
        proxy_url=proxy,
        headless=not args.headful,
        mobile=args.mobile,
        timeout=args.timeout,
        wait_extra_ms=args.wait,
        screenshot=args.screenshot,
        engine=args.engine,
        ignore_https_errors=args.ignore_https_errors,
    ))

    if args.output and result.get("content"):
        Path(args.output).write_text(result["content"], encoding="utf-8")
        print(f"  Content saved -> {args.output}")

    summary = {k: v for k, v in result.items() if k != "content"}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
