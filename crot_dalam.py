#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CROT DALAM — TikTok OSINT (No-API Web Scraper) · Python CLI

Approach
  • Drive a real browser with Playwright (Chromium) to load the public search page.
  • Scroll and collect unique video URLs (no login required).
  • Open each video page and extract metadata from meta tags / structured data / DOM.
  • Heuristic "risk tags" scoring based on keywords (multi-language friendly).

Legal & ethics
  Use responsibly. Respect TikTok's terms and local laws. This is for OSINT on public data only.

Quickstart
  python -m pip install playwright typer rich
  python -m playwright install chromium

  # Basic search (headless)
  python crot_dalam.py search "phishing" "scam" --limit 80 --out out/crot_dalam

  # Visible browser + screenshots + Indonesian locale
  python crot_dalam.py search "promo gratis" --locale id-ID --headless false --screenshot --limit 40

Outputs
  out/<basename>.jsonl   — one JSON object per line
  out/<basename>.csv     — flattened table
  out/screenshots/       — optional PNGs (one per video)

Tested on: Python 3.10+ · Playwright ≥1.44
"""
from __future__ import annotations
import csv
import dataclasses as dc
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import typer
from rich import print as rprint
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from urllib.parse import urlparse, parse_qs, quote_plus

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
BANNER = r"""
   █████████                      █████       ██████████             ████                              
  ███░░░░░███                    ░░███       ░░███░░░░███           ░░███                              
 ███     ░░░  ████████   ██████  ███████      ░███   ░░███  ██████   ░███   ██████   █████████████     
░███         ░░███░░███ ███░░███░░░███░       ░███    ░███ ░░░░░███  ░███  ░░░░░███ ░░███░░███░░███    
░███          ░███ ░░░ ░███ ░███  ░███        ░███    ░███  ███████  ░███   ███████  ░███ ░███ ░███    
░░███     ███ ░███     ░███ ░███  ░███ ███    ░███    ███  ███░░███  ░███  ███░░███  ░███ ░███ ░███    
 ░░█████████  █████    ░░██████   ░░█████     ██████████  ░░████████ █████░░████████ █████░███ █████   
  ░░░░░░░░░  ░░░░░      ░░░░░░     ░░░░░     ░░░░░░░░░░    ░░░░░░░░ ░░░░░  ░░░░░░░░ ░░░░░ ░░░ ░░░░░    
           
Code By sudo3rs            
"""

SUBTITLE = "Collection & Reconnaissance Of TikTok — Discovery, Analysis, Logging, And Monitoring"

def print_banner() -> None:
    rprint(Panel.fit(BANNER, title="[bold cyan]CROT DALAM[/]", subtitle=SUBTITLE, border_style="cyan"))

app = typer.Typer(add_completion=False, help="CROT‑DALAM — TikTok OSINT by keyword (no API)")

# ---------------------------
# Data models & keyword heuristics
# ---------------------------
@dc.dataclass
class VideoRecord:
    video_id: str
    url: str
    username: Optional[str] = None
    author_name: Optional[str] = None
    description: Optional[str] = None
    upload_date: Optional[str] = None  # ISO8601 if found
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    view_count: Optional[int] = None
    hashtags: List[str] = dc.field(default_factory=list)
    keyword_searched: Optional[str] = None
    risk_score: int = 0
    risk_matches: List[str] = dc.field(default_factory=list)

    def to_row(self) -> Dict[str, Any]:
        d = dc.asdict(self)
        d["hashtags"] = ",".join(self.hashtags)
        d["risk_matches"] = ",".join(self.risk_matches)
        return d

# Common scam/phish terms (EN + ID + generic). Extend as needed.
RISK_TERMS = [
    # English
    r"\b(scams?|phishing|smishing|spoof|giveaway|free\s*iphone|airdrop|crypto\s*giveaway|binary\s*options?|forex\s*signals?)\b",
    r"\b(win\s*(?:cash|money|prize|reward)s?\b)",
    r"\bclick\s*(?:the|this)?\s*link\b",
    r"\bOTP|one[-\s]?time\s*password\b",
    r"\bverification\s*code\b",
    r"\bKYC\b",
    # Indonesian / Bahasa
    r"\bpenipuan|modus|phising|rek\.\?\s*penipu|hadiah\s*gratis|promo\s*gratis|bagi[-\s]?bagi|giveaway\b",
    r"\bklik\s*link|tautan\s*di\s*bio|link\s*di\s*bio\b",
    r"\btransfer\s*dulu|deposit\s*dulu|saldo\s*bonus|langsung\s*cair\b",
    r"\bkode\s*OTP|jangan\s*kasih\s*OTP\b",
]

RISK_RE = [re.compile(pat, re.I) for pat in RISK_TERMS]

# ---------------------------
# Helpers
# ---------------------------

def ensure_out(base: str) -> pathlib.Path:
    p = pathlib.Path(base)
    if p.suffix:
        p = p.with_suffix("")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def parse_username_and_id_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    # e.g., https://www.tiktok.com/@someuser/video/7251234567890123456
    try:
        path = urlparse(url).path.strip("/")
        parts = path.split("/")
        user = None
        vid = None
        for i, part in enumerate(parts):
            if part.startswith("@"):
                user = part[1:]
            if part == "video" and i + 1 < len(parts):
                vid = parts[i + 1].split("?")[0]
        return user, vid
    except Exception:
        return None, None


def to_int_safe(s: Optional[str]) -> Optional[int]:
    if not s:
        return None
    try:
        # Convert TikTok shorthand counts like 1.2M, 3.4K
        m = re.match(r"([0-9]+(?:\.[0-9]+)?)([KkMmBb]?)", s.strip())
        if not m:
            return int(s)
        num = float(m.group(1))
        suf = m.group(2).lower()
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(suf, 1)
        return int(num * mult)
    except Exception:
        return None


def risk_score(text: str) -> Tuple[int, List[str]]:
    text_l = text.lower() if text else ""
    matches = []
    score = 0
    for rx in RISK_RE:
        for m in rx.findall(text_l):
            score += 1
            if isinstance(m, tuple):
                matches.append(next((x for x in m if x), str(m)))
            else:
                matches.append(m if isinstance(m, str) else str(m))
    return score, list(dict.fromkeys(matches))  # dedupe, keep order


# ---------------------------
# Browser routines
# ---------------------------

def new_context(pw, headless: bool, locale: str, user_agent: Optional[str], proxy: Optional[str]):
    launch_args = {"headless": headless, "args": ["--disable-blink-features=AutomationControlled"]}
    if proxy:
        launch_args["proxy"] = {"server": proxy}
    browser = pw.chromium.launch(**launch_args)
    context = browser.new_context(
        locale=locale,
        user_agent=user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
    )
    # Reduce obvious automation fingerprints
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = { runtime: {} };
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        """
    )
    return browser, context


def accept_cookies_if_any(page) -> None:
    try:
        page.click("text=/Accept All|Accept all|I agree|AGREE/i", timeout=3000)
    except PWTimeout:
        pass
    except Exception:
        pass


def search_collect_video_urls(page, query: str, limit: int, per_scroll_wait: float = 1.5) -> List[str]:
    url = f"https://www.tiktok.com/search?q={quote_plus(query)}"
    page.goto(url, wait_until="domcontentloaded")
    accept_cookies_if_any(page)

    seen = set()
    last_count = 0
    stagnant_rounds = 0

    while len(seen) < limit and stagnant_rounds < 8:
        # Gather anchors pointing to video pages
        anchors = page.query_selector_all("a[href*='/video/']")
        for a in anchors:
            href = a.get_attribute("href")
            if not href:
                continue
            if href.startswith("/"):
                href = "https://www.tiktok.com" + href
            if "/video/" in href:
                seen.add(href.split("?")[0])
                if len(seen) >= limit:
                    break
        # Scroll to load more
        page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
        time.sleep(per_scroll_wait)
        if len(seen) == last_count:
            stagnant_rounds += 1
        else:
            stagnant_rounds = 0
        last_count = len(seen)
    return list(seen)[:limit]


def extract_video_metadata(page, url: str) -> VideoRecord:
    # Open page and mine structured signals
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        accept_cookies_if_any(page)
    except PWTimeout:
        pass

    # 1) Try JSON-LD
    desc = None
    upload_date = None
    author_name = None
    view_count = like_count = comment_count = share_count = None
    hashtags: List[str] = []

    try:
        for script in page.query_selector_all('script[type="application/ld+json"]'):
            try:
                data = json.loads(script.inner_text())
            except Exception:
                continue
            nodes = data if isinstance(data, list) else [data]
            for n in nodes:
                if not isinstance(n, dict):
                    continue
                if n.get("@type") in ("VideoObject", "SocialMediaPosting"):
                    desc = n.get("description") or desc
                    upload_date = n.get("uploadDate") or n.get("datePublished") or upload_date
                    author = n.get("author")
                    if isinstance(author, dict):
                        author_name = author.get("name") or author_name
                    vc = n.get("interactionStatistic")
                    if isinstance(vc, list):
                        for st in vc:
                            itype = (st or {}).get("interactionType") or ""
                            count = to_int_safe(str((st or {}).get("userInteractionCount", "")))
                            if not count:
                                continue
                            s = json.dumps(itype).lower()
                            if "view" in s or "watch" in s:
                                view_count = view_count or count
                            elif "like" in s:
                                like_count = like_count or count
                            elif "comment" in s:
                                comment_count = comment_count or count
                            elif "share" in s:
                                share_count = share_count or count
    except Exception:
        pass

    # 2) Meta tags fallback
    try:
        og_desc = page.locator('meta[property="og:description"]').first.get_attribute("content")
        if og_desc:
            desc = desc or og_desc
    except Exception:
        pass

    # 3) DOM selectors fallback
    try:
        # Hashtags from anchors
        for a in page.query_selector_all("a[href^='/tag/'], a[href*='tiktok.com/tag/']"):
            text = (a.inner_text() or "").strip()
            if text.startswith('#'):
                hashtags.append(text[1:])
    except Exception:
        pass

    # Username & Video ID via URL parsing
    username, vid = parse_username_and_id_from_url(url)

    # Risk scoring
    score, matches = risk_score(desc or "")

    return VideoRecord(
        video_id=vid or "",
        url=url,
        username=username,
        author_name=author_name,
        description=desc,
        upload_date=upload_date,
        like_count=like_count,
        comment_count=comment_count,
        share_count=share_count,
        view_count=view_count,
        hashtags=sorted(set(hashtags)),
        risk_score=score,
        risk_matches=matches,
    )


# ---------------------------
# I/O
# ---------------------------

def write_outputs(records: List[VideoRecord], base: pathlib.Path, do_screens: bool, shots_dir: pathlib.Path, ctx) -> None:
    jsonl = base.with_suffix('.jsonl')
    csvp = base.with_suffix('.csv')

    with jsonl.open('w', encoding='utf-8') as jf:
        for r in records:
            jf.write(json.dumps(r.to_row(), ensure_ascii=False) + '\n')

    fields = list(VideoRecord.__annotations__.keys())
    with csvp.open('w', encoding='utf-8', newline='') as cf:
        w = csv.DictWriter(cf, fieldnames=fields)
        w.writeheader()
        for r in records:
            w.writerow(r.to_row())

    rprint(f"[bold green]Saved[/]: {jsonl}")
    rprint(f"[bold green]Saved[/]: {csvp}")


# ---------------------------
# CLI
# ---------------------------
@app.command()
def search(
    keyword: List[str] = typer.Argument(..., help="One or more keywords to search on TikTok"),
    limit: int = typer.Option(60, min=1, max=600, help="Max videos to collect (approx)"),
    out: str = typer.Option("out/crot_dalam", help="Output basename (no extension)"),
    headless: bool = typer.Option(True, help="Run headless browser"),
    locale: str = typer.Option("en-US", help="Browser locale like en-US or id-ID"),
    user_agent: Optional[str] = typer.Option(None, help="Custom User-Agent"),
    proxy: Optional[str] = typer.Option(None, help="Proxy, e.g. http://user:pass@host:port"),
    screenshot: bool = typer.Option(False, help="Save per-video page screenshot"),
    per_keyword_limit: Optional[int] = typer.Option(None, help="Override per-keyword cap; default shares --limit across all"),
):
    """Search TikTok public UI for each KEYWORD and export JSONL/CSV (no API keys)."""
    print_banner()
    base = ensure_out(out)
    shots_dir = base.parent / "screenshots"
    if screenshot:
        shots_dir.mkdir(parents=True, exist_ok=True)

    total_target = limit
    rprint(f"[bold]CROT-DALAM[/] starting… keywords={keyword} headless={headless} locale={locale}")

    with sync_playwright() as pw:
        browser, ctx = new_context(pw, headless=headless, locale=locale, user_agent=user_agent, proxy=proxy)
        page = ctx.new_page()
        collected: List[VideoRecord] = []
        seen_urls: set[str] = set()

        try:
            for kw in keyword:
                if len(collected) >= total_target:
                    break
                cap = per_keyword_limit or max(1, (total_target - len(collected)) // max(1, (len(keyword))))
                urls = search_collect_video_urls(page, kw, cap)
                rprint(f"[cyan]Found ~{len(urls)} video URLs for[/] '{kw}'")
                for url in urls:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    vp = ctx.new_page()
                    rec = extract_video_metadata(vp, url)
                    vp.wait_for_timeout(300)  # brief quiet
                    if screenshot and rec.video_id:
                        try:
                            shot_path = shots_dir / f"{rec.video_id}.png"
                            vp.screenshot(path=str(shot_path), full_page=True)
                        except Exception:
                            pass
                    vp.close()

                    rec.keyword_searched = kw
                    collected.append(rec)

                    if len(collected) >= total_target:
                        break
        finally:
            try:
                page.close()
                ctx.close()
                browser.close()
            except Exception:
                pass

    # Post-process: risk scoring already done per record
    write_outputs(collected, base, screenshot, shots_dir, ctx=None)

    # Console summary
    tbl = Table(title="CROT-DALAM Summary")
    tbl.add_column("Videos", justify="right")
    tbl.add_column("Keywords")
    tbl.add_column("Avg Risk")
    if collected:
        from statistics import mean
        tbl.add_row(str(len(collected)), ", ".join(keyword), f"{mean([r.risk_score for r in collected]):.2f}")
    else:
        tbl.add_row("0", ", ".join(keyword), "0.00")
    rprint(tbl)


if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)
