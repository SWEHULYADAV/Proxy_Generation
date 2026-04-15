#!/usr/bin/env python3
"""
🚀 ADVANCED PROXY HARVESTER (CLEAN)
— Single JSON, real-time updates of ONLY active proxies —

- Async collection & validation (aiohttp)
- Optional Rich dashboard (if installed)
- Real-time JSON write (only active proxies)
"""

import asyncio
import aiohttp
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Set
from dataclasses import dataclass, asdict, field

# Optional Rich UI
try:
    from rich.console import Console
    from rich.table import Table
    from rich import box
    RICH_AVAILABLE = True
    console = Console()
except ImportError:
    RICH_AVAILABLE = False
    class _C:
        def print(self, *a, **k): print(*a)
    console = _C()

# ========= Data Model =========

@dataclass
class ProxyStats:
    proxy: str
    first_seen: datetime
    last_seen: datetime
    total_checks: int = 0
    successful_checks: int = 0
    response_times: List[float] = field(default_factory=list)
    uptime_seconds: float = 0.0
    country: str = ""
    success_rate: float = 0.0
    avg_response_time: float = 0.0
    score: float = 0.0

    def update_success(self, response_time: float):
        self.total_checks += 1
        self.successful_checks += 1
        self.response_times.append(response_time)
        if len(self.response_times) > 10:
            self.response_times = self.response_times[-10:]
        self.last_seen = datetime.now()
        self._recalc()

    def update_failure(self):
        self.total_checks += 1
        # keep last_seen untouched on failure to reflect last success
        self._recalc()
        # slight penalty
        self.score *= 0.95

    def _recalc(self):
        self.success_rate = (self.successful_checks / self.total_checks) if self.total_checks else 0.0
        self.avg_response_time = (sum(self.response_times) / len(self.response_times)) if self.response_times else 10.0
        self.uptime_seconds = max(0.0, (self.last_seen - self.first_seen).total_seconds())
        # Score = 40% uptime (cap 24h) + 30% success + 30% speed(<=10s)
        uptime_score = min(self.uptime_seconds / 86400.0, 1.0) * 0.4
        success_score = self.success_rate * 0.3
        speed_score = max(0.0, (10.0 - self.avg_response_time) / 10.0) * 0.3
        self.score = uptime_score + success_score + speed_score


# ========= Harvester =========

class AdvancedProxyHarvester:
    def __init__(self):
        self.stats: Dict[str, ProxyStats] = {}
        self.active_proxies: Set[str] = set()
        self.session: aiohttp.ClientSession | None = None

        # Config
        self.config = {
            'max_concurrent': 200,
            'timeout': 8,
            'update_interval': 120,   # collect new sources
            'verify_interval': 60,    # re-verify pool
            'auto_save_interval': 15, # JSON flush
            'max_proxies': 2000,      # soft cap
            'min_success_rate': 0.5,
            'output_file': 'active_proxies.json',
        }

        # Fresh sources
        self.sources = [
            'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all.txt',
            'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/http.txt',
            'https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt',
            'https://raw.githubusercontent.com/zloi-user/hideip.me/main/https.txt',
            'https://raw.githubusercontent.com/gitrecon1455/fresh-proxy-list/main/all.txt',
            'https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/http.txt',
            'https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/https.txt',
            'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
            'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt',
            'https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/proxies/http.txt',
            'https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt',
            'https://api.proxyscrape.com/v2/?request=get&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all',
            'https://www.proxy-list.download/api/v1/get?type=http',
            'https://api.openproxylist.xyz/http.txt',
            'https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt',
            'https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt',
            'https://raw.githubusercontent.com/mertguvencli/http-proxy-list/main/proxy-list/data.txt',
            'https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt',
            'https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt',
            'https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt',
        ]

        # Internal timers
        self._last_collect = 0.0
        self._last_verify = 0.0
        self._last_auto_save = 0.0

    # ---- lifecycle ----
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=self.config['max_concurrent'])
        timeout = aiohttp.ClientTimeout(total=self.config['timeout'])
        self.session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        self._load_active_json()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.session:
            await self.session.close()

    # ---- persistence (SINGLE JSON only) ----
    def _load_active_json(self):
        path = Path(self.config['output_file'])
        if not path.exists():
            console.print("📊 No previous state found. Starting fresh.")
            return
        try:
            raw = json.loads(path.read_text(encoding='utf-8'))
            items = raw.get("proxies", [])
            count = 0
            for item in items:
                proxy = item["proxy"]
                fs = datetime.fromisoformat(item["first_seen"])
                ls = datetime.fromisoformat(item["last_seen"])
                ps = ProxyStats(
                    proxy=proxy,
                    first_seen=fs,
                    last_seen=ls,
                    total_checks=item.get("total_checks", 0),
                    successful_checks=item.get("successful_checks", 0),
                    response_times=item.get("response_times", []),
                    uptime_seconds=item.get("uptime_seconds", 0.0),
                    country=item.get("country", ""),
                    success_rate=item.get("success_rate", 0.0),
                    avg_response_time=item.get("avg_response_time", 0.0),
                    score=item.get("score", 0.0),
                )
                self.stats[proxy] = ps
                self.active_proxies.add(proxy)
                count += 1
            console.print(f"✅ Loaded {count} active proxies from JSON.")
        except Exception as e:
            console.print(f"⚠️ Could not load active JSON: {e}. Starting fresh.")

    def _save_active_json(self, force=False):
        now = time.time()
        if not force and (now - self._last_auto_save) < self.config['auto_save_interval']:
            return
        # Build sorted list by score
        sorted_items = sorted(
            (p for p in self.active_proxies if p in self.stats),
            key=lambda p: self.stats[p].score,
            reverse=True
        )
        data = {
            "updated_at": datetime.now().isoformat(timespec='seconds'),
            "count": len(sorted_items),
            "proxies": [
                {
                    **{
                        k: (v.isoformat() if isinstance(v, datetime) else v)
                        for k, v in asdict(self.stats[p]).items()
                    }
                }
                for p in sorted_items
            ]
        }
        try:
            Path(self.config['output_file']).write_text(json.dumps(data, indent=2), encoding='utf-8')
            self._last_auto_save = now
            console.print(f"💾 JSON updated: {data['count']} active proxies")
        except Exception as e:
            console.print(f"❌ Failed to write JSON: {e}")

    # ---- utils ----
    @staticmethod
    def _extract_proxies(text: str) -> Set[str]:
        # ip:port
        pattern = r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}\b'
        return set(re.findall(pattern, text))

    async def _fetch_source(self, url: str) -> Set[str]:
        try:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    txt = await resp.text()
                    proxies = self._extract_proxies(txt)
                    if proxies:
                        console.print(f"✅ {url[:60]}... -> {len(proxies)}")
                    return proxies
        except Exception:
            pass
        console.print(f"❌ {url[:60]}... failed")
        return set()

    async def _collect_all(self) -> Set[str]:
        console.print("🔄 Collecting proxies from sources...")
        tasks = [self._fetch_source(u) for u in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        all_set: Set[str] = set()
        for r in results:
            if isinstance(r, set):
                all_set |= r
        # soft cap
        if len(all_set) > self.config['max_proxies']:
            all_set = set(list(all_set)[:self.config['max_proxies']])
        console.print(f"📊 Collected {len(all_set)} unique proxies")
        return all_set

    async def _test_proxy(self, proxy: str) -> dict:
        # Simple HTTP endpoint; avoid HTTPS to allow plain HTTP proxies
        test_url = 'http://httpbin.org/ip'
        start = time.time()
        try:
            async with self.session.get(test_url, proxy=f'http://{proxy}') as resp:
                rt = time.time() - start
                if resp.status == 200:
                    data = await resp.json()
                    if 'origin' in data:
                        return {"working": True, "response_time": rt}
        except Exception:
            pass
        return {"working": False}

    async def _verify_batch(self, proxies: List[str]) -> List[str]:
        sem = asyncio.Semaphore(self.config['max_concurrent'])
        working: List[str] = []

        async def _one(p: str):
            async with sem:
                res = await self._test_proxy(p)
                st = self.stats.get(p)
                if not st:
                    st = ProxyStats(proxy=p, first_seen=datetime.now(), last_seen=datetime.now())
                    self.stats[p] = st
                if res["working"]:
                    st.update_success(res["response_time"])
                    working.append(p)
                else:
                    st.update_failure()

        await asyncio.gather(*[_one(p) for p in proxies], return_exceptions=True)
        return working

    def _print_dashboard(self):
        if not self.active_proxies:
            return
        top = sorted(self.active_proxies, key=lambda p: self.stats[p].score, reverse=True)[:10]
        if RICH_AVAILABLE:
            table = Table(title="🚀 Active Proxies (Top 10)", box=box.ROUNDED)
            table.add_column("Rank", style="cyan", no_wrap=True)
            table.add_column("Proxy", style="green")
            table.add_column("Score", style="yellow")
            table.add_column("Success %", style="bright_green")
            table.add_column("Speed (s)", style="blue")
            for i, p in enumerate(top, 1):
                s = self.stats[p]
                table.add_row(str(i), p, f"{s.score:.3f}", f"{s.success_rate*100:.1f}", f"{s.avg_response_time:.2f}")
            console.print(table)
        else:
            print("\nTop active proxies:")
            for i, p in enumerate(top, 1):
                s = self.stats[p]
                print(f"{i:>2}. {p} | score {s.score:.3f} | succ {s.success_rate*100:.1f}% | {s.avg_response_time:.2f}s")

    # ---- main loop ----
    async def run(self):
        console.print("🔥 START — Single JSON, real-time active proxies only")
        self._last_collect = time.time() - self.config['update_interval']
        self._last_verify = time.time() - self.config['verify_interval']
        self._last_auto_save = 0.0

        try:
            while True:
                now = time.time()

                # Collect from sources
                if now - self._last_collect >= self.config['update_interval']:
                    all_proxies = await self._collect_all()
                    new_ones = [p for p in all_proxies if p not in self.active_proxies]
                    if new_ones:
                        console.print(f"🔍 Testing {len(new_ones)} new proxies ...")
                        good = await self._verify_batch(new_ones)
                        self.active_proxies.update(good)
                        console.print(f"✅ Added {len(good)} new active proxies")
                    self._last_collect = now

                # Re-verify a slice of existing
                if now - self._last_verify >= self.config['verify_interval']:
                    if self.active_proxies:
                        batch = list(self.active_proxies)[: min(150, len(self.active_proxies))]
                        console.print(f"🔁 Re-verifying {len(batch)} active proxies ...")
                        good = await self._verify_batch(batch)
                        dead = set(batch) - set(good)
                        if dead:
                            self.active_proxies -= dead
                            console.print(f"🗑️ Removed {len(dead)} dead proxies")
                    self._last_verify = now

                # Persist ONLY active proxies
                self._save_active_json()

                # Quick dashboard
                self._print_dashboard()

                # One line status
                if self.active_proxies:
                    best = max(self.active_proxies, key=lambda p: self.stats[p].score)
                    bs = self.stats[best]
                    console.print(f"📊 Active={len(self.active_proxies)} | Best={best} (score {bs.score:.3f})")

                await asyncio.sleep(10)

        except KeyboardInterrupt:
            console.print("\n🛑 Stopped by user. Writing final JSON ...")
            self._save_active_json(force=True)
            console.print(f"✅ Final active count: {len(self.active_proxies)}")
        except Exception as e:
            console.print(f"❌ Unexpected error: {e}")
            self._save_active_json(force=True)
            raise

# ========= Entrypoint =========

async def main():
    async with AdvancedProxyHarvester() as h:
        await h.run()

if __name__ == "__main__":
    asyncio.run(main())
