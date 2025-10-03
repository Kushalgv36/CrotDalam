#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CROT DALAM — TikTok OSINT (No-API Web Scraper) · Python CLI

Highlights (v2025.10.03)
- [NEW] Investigation modes: --mode {quick, moderate, deep, deeper}
- [NEW] URL extraction from video descriptions → CSV/JSONL/HTML
- [NEW] Polished HTML investigation report (responsive table, risk highlighting)
- [IMPROVED] Robust Playwright flows (timeouts, retries, cookie banners, lazy loads)
- [IMPROVED] Safer counters parsing (e.g., 1.2K, 3.4M) & date parsing
- [IMPROVED] Pivot by top hashtags (optional) and basic comment collection
- [IMPROVED] Optional video download via yt-dlp, optional Archive.is snapshot

Quickstart
  python crot_dalam.py search "undian berhadiah" --mode deep --limit 60
  
Outputs
  out/<basename>.jsonl — structured records (one JSON per line)
  out/<basename>.csv   — flat table (for Excel/Sheets)
  out/<basename>.html  — [NEW] clean HTML investigation report

Notes
- Use responsibly. Respect robots, ToS, and local laws. This tool is for OSINT/defense.
- Playwright requires browsers installed. If missing, run: `playwright install chromium`.
"""
from __future__ import annotations

import csv
import dataclasses as dc
import datetime as dt
import enum
import html
import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Any, Deque, Dict, List, Optional, Tuple

import requests
import typer
from rich import print as rprint
from rich.panel import Panel
from rich.table import Table

try:
    from playwright.sync_api import (
        sync_playwright,
        TimeoutError as PWTimeout,
        Error as PlaywrightError,
    )
except Exception as e:  # pragma: no cover
    rprint("[red]Playwright is not available. Install with:[/red] [bold]pip install playwright[/bold]\n"
           "Then run: [bold]playwright install chromium[/bold]")
    raise

# -------------------------------------------------------------
# Banner
# -------------------------------------------------------------
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
    rprint(
        Panel.fit(
            BANNER,
            title="[bold cyan]CROT DALAM[/]",
            subtitle=SUBTITLE,
            border_style="cyan",
        )
    )


# -------------------------------------------------------------
# CLI
# -------------------------------------------------------------
class InvestigationMode(str, enum.Enum):
    quick = "quick"
    moderate = "moderate"
    deep = "deep"
    deeper = "deeper"


app = typer.Typer(add_completion=False, help="CROT‑DALAM — TikTok OSINT by keyword (no API)")


# -------------------------------------------------------------
# Data models & keyword heuristics
# -------------------------------------------------------------
@dc.dataclass
class VideoRecord:
    # Core
    video_id: str
    url: str
    username: Optional[str] = None
    author_name: Optional[str] = None
    description: Optional[str] = None
    upload_date: Optional[str] = None

    # Metrics
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    share_count: Optional[int] = None
    view_count: Optional[int] = None

    # Extras
    hashtags: List[str] = dc.field(default_factory=list)
    comments: List[Dict[str, str]] = dc.field(default_factory=list)
    extracted_urls: List[str] = dc.field(default_factory=list)  # [NEW]
    keyword_searched: Optional[str] = None

    # Risk
    risk_score: int = 0
    risk_matches: List[str] = dc.field(default_factory=list)

    def to_row(self) -> Dict[str, Any]:
        d = dc.asdict(self)
        d["hashtags"] = ", ".join(self.hashtags)
        d["risk_matches"] = ", ".join(self.risk_matches)
        d["comments"] = json.dumps(self.comments, ensure_ascii=False) if self.comments else ""
        d["extracted_urls"] = ", ".join(self.extracted_urls)
        return d


# Common fraud / scam indicators (EN/ID). Non-exhaustive.
RISK_TERMS: List[str] = [
    # ID terms
    "undian berhadiah", "hadiah langsung", "giveaway resmi", "dapat hadiah", "menang undian",
    "hadiah cair", "bagi-bagi saldo", "saldo dana gratis", "saldo gopay gratis", "saldo ovo gratis",
    "investasi cepat", "cuan cepat", "slot gacor", "deposit via dm", "deposit via link",
    "pinjol cair", "pinjaman tanpa agunan", "kerja dari rumah gaji", "kerja online tanpa modal",
    "reseller resmi", "agen resmi", "koin gratis", "kode rahasia",
    "WA admin", "hubungi admin", "dm admin", "langsung chat admin",
    "rekening penampung", "transfer dulu", "biaya admin dulu",
    # EN terms
    "free giveaway", "airdrop", "claim reward", "verify wallet", "seed phrase", "private key",
    "binance bonus", "okx bonus", "bybit bonus", "crypto double", "investment 100% profit",
    "limited slots", "send first", "processing fee", "admin fee", "payment upfront",
]

# Regexes to spot phone/wa numbers, wallets, urls; loose to avoid false negatives
RISK_RE: List[re.Pattern] = [
    re.compile(r"\b(\+?62|0)8\d{8,12}\b"),                 # Indonesian phone/WA
    re.compile(r"\b(?:bc1|[13])[a-zA-HJ-NP-Z0-9]{25,39}\b"),  # BTC wallet-ish
    re.compile(r"\b[Tt]rx[a-zA-Z0-9]{25,34}\b"),              # TRX-ish (loose)
    re.compile(r"\b(?:0x)[0-9A-Fa-f]{40}\b"),                 # ETH/erc20
]


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s\"]+")
_HASHTAG_RE = re.compile(r"(?<!&)#(\w{2,64})", re.UNICODE)
_VIDEO_URL_RE = re.compile(r"/(@[^/]+)/video/(\d+)")


def extract_urls_from_text(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return list(dict.fromkeys(re.findall(_URL_RE, text)))  # dedupe, preserve order


def ensure_out(base: str | pathlib.Path) -> pathlib.Path:
    base = pathlib.Path(base)
    base_dir = base.parent if base.suffix else base.parent
    if str(base).endswith(('.csv', '.jsonl', '.html')):
        base = base.with_suffix("")
    out_dir = base.parent
    if not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
    return base


def run_cmd(cmd: List[str]) -> Tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except Exception as e:  # pragma: no cover
        return 1, "", str(e)


def download_video(video_url: str, download_dir: pathlib.Path) -> bool:
    """Download with yt-dlp if available. Returns True on success."""
    download_dir.mkdir(parents=True, exist_ok=True)
    ytdlp = "yt-dlp"
    out_tpl = str(download_dir / "%(id)s.%(ext)s")
    code, out, err = run_cmd([ytdlp, "--no-warnings", "--no-playlist", "-o", out_tpl, video_url])
    if code == 0:
        rprint(f"[green]yt-dlp downloaded:[/green] {video_url}")
        return True
    rprint(f"[yellow]yt-dlp failed:[/yellow] {err or out}")
    return False


def archive_to_archive_is(url: str, timeout: int = 20) -> Optional[str]:
    """Request an Archive.today snapshot. Returns snapshot URL if visible in response."""
    try:
        resp = requests.post(
            "https://archive.today/submit/",
            data={"url": url},
            timeout=timeout,
            headers={"User-Agent": default_user_agent()},
        )
        # Heuristic: look for Refresh meta or Location header
        loc = resp.headers.get("Content-Location") or resp.headers.get("Location")
        if loc:
            return loc
        m = re.search(r"https?://archive\.(?:today|is|ph)/[\w/\-]+", resp.text)
        return m.group(0) if m else None
    except Exception:
        return None


def parse_username_and_id_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    try:
        m = re.search(_VIDEO_URL_RE, url)
        if not m:
            return None, None
        username = m.group(1).lstrip("@") if m.group(1) else None
        vid = m.group(2)
        return username, vid
    except Exception:
        return None, None


_KSUFFIX = {
    "k": 1_000,
    "K": 1_000,
    "m": 1_000_000,
    "M": 1_000_000,
}


def to_int_safe(s: Optional[str]) -> Optional[int]:
    if s is None:
        return None
    s = s.strip()
    if not s:
        return None
    try:
        # 1.2K, 3.4M, 999, 12,345
        m = re.match(r"([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+(?:\.[0-9]+)?)([kKmM]?)", s)
        if not m:
            return int(re.sub(r"[^0-9]", "", s) or 0)
        num, suf = m.groups()
        num = num.replace(",", "")
        val = float(num)
        if suf:
            val *= _KSUFFIX.get(suf, 1)
        return int(val)
    except Exception:
        return None


def risk_score(text: Optional[str]) -> Tuple[int, List[str]]:
    text = (text or "").lower()
    matches: List[str] = []
    for t in RISK_TERMS:
        if t in text:
            matches.append(t)
    for rx in RISK_RE:
        for m in rx.findall(text):
            s = m if isinstance(m, str) else " ".join([x for x in m if x])
            if s:
                matches.append(str(s))
    dedup = list(dict.fromkeys(matches))
    score = len(dedup)
    # amplify when highly suspicious phrases present
    if any(k in text for k in ["transfer dulu", "seed phrase", "private key", "biaya admin"]):
        score += 2
    return score, dedup


def default_user_agent() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/118.0.0.0 Safari/537.36"
    )


# -------------------------------------------------------------
# Playwright routines
# -------------------------------------------------------------

def new_context(pw, headless: bool, locale: str, user_agent: Optional[str], proxy: Optional[str]):
    args = {
        "headless": headless,
        "channel": None,
    }
    if proxy:
        args["proxy"] = {"server": proxy}
    browser = pw.chromium.launch(**args)
    context = browser.new_context(
        user_agent=user_agent or default_user_agent(),
        locale=locale or "en-US",
        viewport={"width": 1280, "height": 900},
    )
    context.set_default_timeout(15_000)
    return browser, context


def accept_cookies_if_any(page) -> None:
    # Try common consent patterns (multi-language)
    selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Accept All")',
        'button:has-text("Terima semua")',
        'button:has-text("I agree")',
        'button:has-text("Allow all")',
        'button:has-text("AGREE")',
        'button[data-e2e="gdpr-accept-button"]',
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel)
            if btn and btn.count() > 0:
                btn.first.click(timeout=2000)
                time.sleep(0.4)
                break
        except Exception:
            pass


def _scroll_and_collect(page, limit: int, per_scroll_wait: float = 1.2) -> List[str]:
    seen: Dict[str, None] = {}
    last_height = 0
    while len(seen) < limit:
        # Collect anchors with video pattern
        try:
            anchors = page.locator('a[href*="/video/"]').evaluate_all(
                "elements => elements.map(e => e.href)"
            )
        except Exception:
            anchors = []
        for href in anchors or []:
            if "/video/" in href and re.search(_VIDEO_URL_RE, href):
                seen[href] = None
                if len(seen) >= limit:
                    break
        # Scroll down
        try:
            page.mouse.wheel(0, 2000)
            time.sleep(per_scroll_wait)
            page.mouse.wheel(0, 2000)
        except Exception:
            time.sleep(per_scroll_wait)
        # Small escape if no growth
        try:
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
        except Exception:
            pass
    return list(seen.keys())


def search_collect_video_urls(page, query: str, limit: int, per_scroll_wait: float = 1.2) -> List[str]:
    url = f"https://www.tiktok.com/search?q={requests.utils.quote(query)}"
    page.goto(url, wait_until="domcontentloaded")
    accept_cookies_if_any(page)
    time.sleep(1.0)
    urls = _scroll_and_collect(page, limit=limit, per_scroll_wait=per_scroll_wait)
    rprint(f"[cyan]Collected[/cyan] {len(urls)} video URLs for query: [bold]{query}[/bold]")
    return urls


def _text_or_none(locator) -> Optional[str]:
    try:
        if locator and locator.count() > 0:
            t = locator.first.inner_text().strip()
            return t
    except Exception:
        return None
    return None


def _attr_or_none(locator, attr: str) -> Optional[str]:
    try:
        if locator and locator.count() > 0:
            v = locator.first.get_attribute(attr)
            return v
    except Exception:
        return None
    return None


def _collect_hashtags(text: Optional[str]) -> List[str]:
    if not text:
        return []
    return list(dict.fromkeys(m.group(1) for m in _HASHTAG_RE.finditer(text)))


def _parse_date_from_time_tag(page) -> Optional[str]:
    try:
        # Many TikTok pages include <time datetime="2025-09-28T12:34:56Z">
        dt_attr = _attr_or_none(page.locator("time"), "datetime")
        if dt_attr:
            return dt_attr
    except Exception:
        pass
    return None


def _expand_comments_if_possible(page, desired: int) -> None:
    if desired <= 0:
        return
    try:
        for _ in range(5):  # click a few times
            more = page.locator('button:has-text("View more")')
            if more and more.count() > 0:
                more.first.click()
                time.sleep(0.6)
            else:
                break
    except Exception:
        pass


def _collect_comments(page, limit: int) -> List[Dict[str, str]]:
    if limit <= 0:
        return []
    out: List[Dict[str, str]] = []
    try:
        cards = page.locator('[data-e2e="comment-list"] [data-e2e="comment-item"]')
        n = min(cards.count(), limit)
        for i in range(n):
            card = cards.nth(i)
            user = _text_or_none(card.locator('[data-e2e="comment-username"]'))
            text = _text_or_none(card.locator('[data-e2e="comment-content"]'))
            if text:
                out.append({"user": user or "", "text": text})
    except Exception:
        pass
    return out


def extract_video_metadata(page, url: str, comments_limit: int) -> VideoRecord:
    # Open video page
    page.goto(url, wait_until="domcontentloaded")
    accept_cookies_if_any(page)
    time.sleep(0.8)

    # Basic fields (multiple selector attempts for resilience)
    desc = (
        _text_or_none(page.locator('[data-e2e="video-desc"]'))
        or _text_or_none(page.locator('h1[data-e2e="video-desc"]'))
        or _text_or_none(page.locator('div[data-e2e="browse-video-desc"]'))
    )

    author_name = (
        _text_or_none(page.locator('[data-e2e="browse-author-name"]'))
        or _text_or_none(page.locator('[data-e2e="user-card-username"]'))
    )

    like_count = to_int_safe(_text_or_none(page.locator('[data-e2e="like-count"]')))
    comment_count = to_int_safe(_text_or_none(page.locator('[data-e2e="comment-count"]')))
    share_count = to_int_safe(_text_or_none(page.locator('[data-e2e="share-count"]')))
    view_count = to_int_safe(_text_or_none(page.locator('[data-e2e="view-count"]')))

    upload_date = _parse_date_from_time_tag(page)

    hashtags = _collect_hashtags(desc)

    _expand_comments_if_possible(page, comments_limit)
    comments_data = _collect_comments(page, comments_limit)

    username, vid = parse_username_and_id_from_url(url)
    score, matches = risk_score(desc)
    extracted_urls = extract_urls_from_text(desc)

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
        comments=comments_data,
        extracted_urls=extracted_urls,
        risk_score=score,
        risk_matches=matches,
    )


# -------------------------------------------------------------
# Output writers
# -------------------------------------------------------------

def write_outputs(records: List[VideoRecord], base: pathlib.Path) -> Tuple[pathlib.Path, pathlib.Path]:
    jsonl = base.with_suffix(".jsonl")
    csvp = base.with_suffix(".csv")

    # JSONL
    with jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(dc.asdict(r), ensure_ascii=False) + "\n")

    # CSV
    fieldnames = list(VideoRecord.__dataclass_fields__.keys())
    with csvp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in records:
            w.writerow(r.to_row())

    rprint(f"[bold green]Saved[/]: {jsonl}")
    rprint(f"[bold green]Saved[/]: {csvp}")
    return jsonl, csvp


def write_html_report(records: List[VideoRecord], base: pathlib.Path, keywords: List[str], mode: str) -> pathlib.Path:
    html_path = base.with_suffix(".html")

    html_css = """
    <style>
        :root { color-scheme: light dark; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 40px; background-color: #f8f9fa; color: #343a40; }
        h1, h2 { color: #0056b3; border-bottom: 2px solid #dee2e6; padding-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        th, td { padding: 12px 15px; border: 1px solid #dee2e6; text-align: left; vertical-align: top; }
        thead { background-color: #007bff; color: #ffffff; }
        tbody tr:nth-of-type(even) { background-color: #f2f2f2; }
        tbody tr:hover { background-color: #e2e6ea; }
        a { color: #0056b3; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .risk-high { background-color: #ffcdd2; font-weight: bold; }
        .risk-medium { background-color: #fff9c4; }
        .url-list { list-style-type: none; padding-left: 0; margin: 0; }
        .url-list li { margin-bottom: 4px; }
        .code { background-color: #e9ecef; padding: 2px 6px; border-radius: 4px; font-family: "Courier New", Courier, monospace; }
        .muted { opacity: .8; }
    </style>
    """

    # Sort by risk desc then likes desc
    records_sorted = sorted(records, key=lambda r: (-(r.risk_score or 0), -(r.like_count or 0)))

    def _urls_html(lst: List[str]) -> str:
        if not lst:
            return "<span class='muted'>—</span>"
        return "<ul class='url-list'>" + "".join(
            f"<li><a href='{html.escape(u)}' target='_blank' rel='noopener'>{html.escape(u)}</a></li>" for u in lst
        ) + "</ul>"

    rows = []
    for r in records_sorted:
        risk_class = "risk-high" if (r.risk_score or 0) >= 3 else ("risk-medium" if (r.risk_score or 0) > 0 else "")
        rows.append(
            f"""
            <tr class='{risk_class}'>
                <td><a href='{html.escape(r.url)}' target='_blank' rel='noopener'>{html.escape(r.video_id or '—')}</a><br/><span class='muted'>@{html.escape(r.username or '')}</span></td>
                <td>{html.escape(r.description or '')}</td>
                <td>{_urls_html(r.extracted_urls)}</td>
                <td>{r.risk_score} <br/><small>{html.escape(', '.join(r.risk_matches))}</small></td>
                <td>{r.like_count or ''}</td>
                <td>{r.comment_count or ''}</td>
                <td>{r.share_count or ''}</td>
                <td>{r.view_count or ''}</td>
                <td>{html.escape(', '.join(r.hashtags))}</td>
                <td>{html.escape(r.upload_date or '')}</td>
            </tr>
            """
        )

    html_doc = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8"/>
        <meta name="viewport" content="width=device-width, initial-scale=1"/>
        <title>CROT DALAM — Laporan Investigasi</title>
        {html_css}
    </head>
    <body>
        <h1>CROT DALAM — Laporan Investigasi</h1>
        <h2>Ringkasan Pencarian</h2>
        <p><strong>Waktu Laporan:</strong> {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Kata Kunci:</strong> {' , '.join(f"<span class=code>{html.escape(k)}</span>" for k in keywords)}</p>
        <p><strong>Mode Investigasi:</strong> <span class="code">{html.escape(mode)}</span></p>
        <p><strong>Total Video Ditemukan:</strong> {len(records)}</p>

        <h2>Hasil Investigasi</h2>
        <table>
            <thead>
                <tr>
                    <th>Video / User</th>
                    <th>Deskripsi</th>
                    <th>URL Ekstraksi</th>
                    <th>Risk</th>
                    <th>Likes</th>
                    <th>Comments</th>
                    <th>Shares</th>
                    <th>Views</th>
                    <th>Hashtags</th>
                    <th>Tanggal</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </body>
    </html>
    """

    with html_path.open("w", encoding="utf-8") as f:
        f.write(html_doc)

    rprint(f"[bold green]Saved[/]: [underline]{html_path}[/underline]")
    return html_path


# -------------------------------------------------------------
# CLI Command: search
# -------------------------------------------------------------

@app.command()
def search(
    keyword: List[str] = typer.Argument(..., help="Satu atau lebih kata kunci untuk dicari di TikTok (kutip untuk frasa)"),
    mode: InvestigationMode = typer.Option(InvestigationMode.quick, case_sensitive=False, help="Pilih mode investigasi untuk preset opsi."),
    limit: int = typer.Option(60, min=1, max=1000, help="Perkiraan jumlah video untuk dikumpulkan per query"),
    out: str = typer.Option("out/crot_dalam", help="Nama file output (tanpa ekstensi)"),
    headless: bool = typer.Option(True, help="Jalankan browser tanpa GUI"),
    locale: str = typer.Option("en-US", help="Locale browser seperti en-US atau id-ID"),
    screenshot: bool = typer.Option(False, help="[Mode] Simpan screenshot halaman per video"),
    download: bool = typer.Option(False, help="[Mode] Unduh video menggunakan yt-dlp"),
    web_archive: bool = typer.Option(False, help="[Mode] Kirim URL ke Archive.is untuk snapshot"),
    comments: int = typer.Option(0, min=0, help="[Mode] Scrape sejumlah komentar per video."),
    pivot_hashtags: int = typer.Option(0, min=0, help="[Mode] Otomatis cari N hashtag teratas."),
    proxy: Optional[str] = typer.Option(None, help="Proxy, cth. http://user:pass@host:port"),
    user_agent: Optional[str] = typer.Option(None, help="Custom User-Agent"),
):
    """Mencari di TikTok menggunakan UI publik dan mengekspor hasilnya."""
    print_banner()

    # Apply mode presets unless overridden by user
    if mode == InvestigationMode.moderate:
        screenshot = True or screenshot
        comments = comments or 5
    elif mode == InvestigationMode.deep:
        screenshot = True or screenshot
        download = True or download
        web_archive = True or web_archive
        comments = comments or 15
        pivot_hashtags = pivot_hashtags or 3
    elif mode == InvestigationMode.deeper:
        screenshot = True or screenshot
        download = True or download
        web_archive = True or web_archive
        comments = comments or 30
        pivot_hashtags = pivot_hashtags or 5

    rprint(f"[bold]Mode Investigasi: [cyan]{mode.value}[/cyan][/bold]")

    base = ensure_out(out)
    searched_keywords: List[str] = [" ".join(keyword).strip()] if len(keyword) > 0 else []
    if len(keyword) > 1:  # If passed as multiple tokens without quotes
        joined = " ".join(keyword)
        if joined not in searched_keywords:
            searched_keywords.append(joined)

    collected: List[VideoRecord] = []

    with sync_playwright() as pw:
        browser, context = new_context(pw, headless=headless, locale=locale, user_agent=user_agent, proxy=proxy)
        try:
            page = context.new_page()
            all_urls: List[str] = []

            for kw in searched_keywords:
                urls = search_collect_video_urls(page, kw, limit=limit)
                all_urls.extend(urls)

            # Pivot by top hashtags (optional)
            if pivot_hashtags > 0:
                rprint("[bold cyan]Pivoting by top hashtags…[/bold cyan]")
                temp_descs = []
                # quickly visit a subset to collect hashtags
                for u in all_urls[:min(len(all_urls), 20)]:
                    page.goto(u, wait_until="domcontentloaded")
                    desc = (
                        _text_or_none(page.locator('[data-e2e="video-desc"]'))
                        or _text_or_none(page.locator('h1[data-e2e="video-desc"]'))
                        or ""
                    )
                    temp_descs.append(desc)
                tags: Dict[str, int] = {}
                for d in temp_descs:
                    for t in _collect_hashtags(d):
                        tags[t] = tags.get(t, 0) + 1
                top_tags = sorted(tags.items(), key=lambda x: -x[1])[:pivot_hashtags]
                for tag, _ in top_tags:
                    q = f"#{tag}"
                    searched_keywords.append(q)
                    urls = search_collect_video_urls(page, q, limit=max(10, limit // 2))
                    all_urls.extend(urls)

            # Deduplicate while preserving order
            seen = set()
            final_urls: List[str] = []
            for u in all_urls:
                if u not in seen:
                    seen.add(u)
                    final_urls.append(u)

            rprint(f"[bold]Total unique URLs to process:[/bold] {len(final_urls)}")

            # Process each video
            for idx, url in enumerate(final_urls, 1):
                try:
                    rec = extract_video_metadata(page, url, comments_limit=comments)
                    rec.keyword_searched = ", ".join(searched_keywords)
                    collected.append(rec)

                    # Modes
                    if screenshot:
                        shot_dir = base.parent / "screenshots"
                        shot_dir.mkdir(parents=True, exist_ok=True)
                        png_path = shot_dir / f"{rec.video_id or idx}.png"
                        page.screenshot(path=str(png_path), full_page=True)

                    if download:
                        dl_dir = base.parent / "videos"
                        download_video(url, dl_dir)

                    if web_archive:
                        snap = archive_to_archive_is(url)
                        if snap:
                            rprint(f"[green]Archived:[/green] {snap}")

                except (PWTimeout, PlaywrightError) as e:
                    rprint(f"[yellow]Playwright warning on {url}:[/yellow] {e}")
                except Exception as e:  # resilient loop
                    rprint(f"[red]Error processing {url}:[/red] {e}")
                # polite pacing
                time.sleep(0.4)
        finally:
            context.close()
            browser.close()

    # Write outputs
    write_outputs(collected, base)
    write_html_report(collected, base, list(dict.fromkeys(searched_keywords)), mode.value)

    # Console summary
    high_risk = sum(1 for r in collected if r.risk_score >= 3)
    rprint(
        f"[bold]\nSummary[/bold]: total={len(collected)} | high‑risk>={3}: {high_risk} | out base: {base}"
    )


# -------------------------------------------------------------
# Entrypoint
# -------------------------------------------------------------
if __name__ == "__main__":
    try:
        app()
    except KeyboardInterrupt:
        rprint("\n[red]Interrupted by user[/red]")
