## 🖼️ CROT DALAM — TikTok OSINT (No-API)

```
█████████                      █████       ██████████             ████                              
  ███░░░░░███                    ░░███       ░░███░░░░███           ░░███                              
 ███     ░░░  ████████   ██████  ███████      ░███   ░░███  ██████   ░███   ██████   █████████████    
░███         ░░███░░███ ███░░███░░░███░       ░███    ░███ ░░░░░███  ░███  ░░░░░███ ░░███░░███░░███   
░███          ░███ ░░░ ░███ ░███  ░███        ░███    ░███  ███████  ░███   ███████  ░███ ░███ ░███   
░░███     ███ ░███     ░███ ░███  ░███ ███    ░███    ███  ███░░███  ░███  ███░░███  ░███ ░███ ░███   
 ░░█████████  █████    ░░██████   ░░█████     ██████████  ░░████████ █████░░████████ █████░███ █████  
  ░░░░░░░░░  ░░░░░      ░░░░░░     ░░░░░     ░░░░░░░░░░    ░░░░░░░░ ░░░░░  ░░░░░░░░ ░░░░░ ░░░ ░░░░░   
           
Code By sudo3rs
Collection & Reconnaissance Of TikTok — Discovery, Analysis, Logging, And Monitoring
```

---


> **C**ollection & **R**econnaissance **O**f **T**ikTok — **D**iscovery, **A**nalysis, **L**ogging, **A**nd **M**onitoring

**CROT DALAM** is a Python CLI that performs **OSINT on TikTok without any API keys**. It drives a real Chromium browser (via Playwright) to search public TikTok pages by keyword, extracts video metadata, applies scam/phishing **risk heuristics** (EN/ID), and exports **JSONL, CSV, and HTML** (plus optional **screenshots**, **video downloads**, and **Archive.today** snapshots).

> ⚠️ For public OSINT only. Respect local laws and platform terms. Do **not** use on private data or accounts.

---

## 🆕 What's New (2025-10-03)

- **Investigation Modes**: `--mode {quick|moderate|deep|deeper}` presets screenshots/comments/pivot/download/archive.
- **URL Extraction** from descriptions → appears in **CSV/JSONL/HTML**.
- **HTML Report**: clean, sortable-friendly table with risk highlighting.
- **Robust scraping**: better selectors, cookie-banner handling, lazy-load scroll, and improved error handling.
- **Metrics parsing**: safe parsing for `1.2K`, `3.4M`, commas, etc.
- **Date parsing** from `<time datetime="…">` when available.
- **Hashtag Pivot**: `--pivot-hashtags N` auto-expands search to top hashtags found.
- **Comment Scraping**: `--comments N` collects top comments for context.
- **Video Downloads**: via **yt-dlp** with **autodetect** fallback to `python -m yt_dlp`.
- **New flag** `--ytdlp-bin` and **env** `YTDLP_BIN` for custom locations.
- **Archive.today snapshots**: `--web-archive` posts URLs for archiving.

---

## ✨ Features

- **No API keys** – scrapes public search & video pages using Playwright
- **Keyword OSINT** – search multiple keywords in one run
- **Risk scoring** – heuristic match for scam/phishing/fake promo terms (EN & Bahasa Indonesia)
- **Entity hints** – extract **hashtags**, **URLs**, **basic comments**
- **Evidence** – optional full-page **screenshots**, optional **video downloads** (yt-dlp), and **Archive.today** snapshots
- **Exports** – structured **JSONL/CSV** + polished **HTML report**
- **Controls** – headless/visible mode, locale, proxy, custom UA, per-keyword caps, investigation modes

---

## 🧠 How it Works

### High Level
```mermaid
flowchart TD
    A([Start CLI<br/>args: keywords, limit, locale...]) --> B[Launch Chromium<br/>Playwright context]
    B --> C[Open TikTok Search<br/>?q=&lt;keyword&gt;]
    C --> D[Infinite scroll<br/>collect /video/ links]
    D --> E[Visit each video]
    E --> F[Extract metadata<br/>JSON-LD, meta tags, DOM]
    F --> G[Risk scoring<br/>regex EN/ID]
    G --> H[Optional screenshot<br/>PNG]
    H --> I[Accumulate records]
    I --> J[Write JSONL + CSV]
    J --> K[Console summary]
```

### Sequence (simplified)

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as crot_dalam.py
    participant PW as Playwright Chromium
    participant T as TikTok (public)

    U->>CLI: search "undian berhadiah" --mode deep --limit 60
    CLI->>PW: Launch context (locale, UA, proxy)
    PW->>T: GET /search?q=...
    T-->>PW: Results page
    CLI->>PW: Scroll & collect /video/ links
    loop For each video
        PW->>T: GET /@user/video/<id>
        T-->>PW: Video page
        CLI->>PW: Extract desc/metrics/hashtags/date/comments
        CLI->>CLI: risk_score(desc) & extract_urls(desc)
        alt Mode options
            CLI->>PW: Screenshot / yt‑dlp / Archive.today
        end
    end
    CLI-->>U: Save .jsonl, .csv, .html (+ evidence dirs)
```

---

## 🧰 Installation

```bash
# Python 3.10+
python -m pip install playwright typer rich requests
python -m playwright install chromium

# (Optional) yt-dlp for video downloads
# Windows (choose one):
winget install yt-dlp.yt-dlp
# or
choco install yt-dlp
# Cross-platform alternatives:
pipx install yt-dlp
# or
python -m pip install --user yt-dlp
```

> **Windows PATH tip** (if using `pip --user`): add something like `C:\\Users\\<USER>\\AppData\\Roaming\\Python\\Python3X\\Scripts` to your PATH, then open a new terminal.

Validate installs:

```bash
playwright --version
where yt-dlp   # Windows
which yt-dlp   # macOS/Linux
```

---

## 🚀 Usage

### Quickstart

```bash
python crot_dalam.py search "undian berhadiah" --mode deep --limit 60 --out out/crot_dalam
```

### Common Examples

```bash
# Visible browser + Indonesian locale + screenshots
python crot_dalam.py search "promo gratis" --locale id-ID --headless false --screenshot --limit 40

# Pivot by top 3 hashtags found + collect 15 comments per video
python crot_dalam.py search "giveaway resmi" --pivot-hashtags 3 --comments 15 --limit 80

# Deep mode + downloads + archive snapshots
python crot_dalam.py search "transfer dulu" --mode deep --download --web-archive --limit 50

# Custom UA + Proxy
python crot_dalam.py search "binary option" --user-agent "Mozilla/5.0 ..." \
  --proxy http://user:pass@host:port --limit 30

# If yt-dlp is installed in a custom path
python crot_dalam.py search "undian berhadiah" --download --ytdlp-bin "C:\\Tools\\yt-dlp.exe"

# Or use Python module launcher as a fallback
set YTDLP_BIN=python
python crot_dalam.py search "undian berhadiah" --download
```

### Outputs

```
out/
  ├─ crot_dalam.jsonl   # one JSON object per line
  ├─ crot_dalam.csv     # flat table with common fields
  ├─ crot_dalam.html    # polished HTML report (risk highlights, URLs)
  ├─ screenshots/       # optional PNGs (one per video)
  └─ videos/            # optional downloads via yt-dlp
```

---

## 🔧 CLI Options (key)

| Option                     | Type                            | Default          | Description                                                         |
| -------------------------- | ------------------------------- | ---------------- | ------------------------------------------------------------------- |
| `keyword...`               | list[str]                       | –                | One or more keywords to search (quote for phrases)                  |
| `--mode`                   | `quick\\|moderate\\|deep\\|deeper` | `quick`          | Investigation presets (screenshots/comments/pivot/download/archive) |
| `--limit`                  | int                             | `60`             | Approx. max videos per query                                        |
| `--out`                    | path                            | `out/crot_dalam` | Output basename (no extension)                                      |
| `--headless/--no-headless` | bool                            | `True`           | Headless browser toggle                                             |
| `--locale`                 | str                             | `en-US`          | Browser locale (e.g., `id-ID`)                                      |
| `--screenshot`             | bool                            | `False`          | Save full-page PNG per video                                        |
| `--download`               | bool                            | `False`          | Download videos via yt-dlp                                          |
| `--web-archive`            | bool                            | `False`          | Submit URLs to Archive.today                                        |
| `--comments`               | int                             | `0`              | Scrape N comments per video                                         |
| `--pivot-hashtags`         | int                             | `0`              | Auto-search top N hashtags found                                    |
| `--proxy`                  | str                             | –                | `http://user:pass@host:port`                                        |
| `--user-agent`             | str                             | –                | Custom UA string                                                    |
| `--ytdlp-bin`              | str                             | –                | Path/name of yt-dlp binary (or set `YTDLP_BIN`)                     |

---

## 🔎 Risk Heuristics (examples)

- **EN**: `free giveaway`, `airdrop`, `verify wallet`, `seed phrase`, `private key`, `limited slots`, `processing fee`, `send first` …
- **ID**: `undian berhadiah`, `bagi-bagi saldo`, `transfer dulu`, `biaya admin dulu`, `pinjol cair`, `slot gacor`, `hubungi admin`, `kode rahasia` …
- **Regex hints**: Indonesian phone/WA, crypto wallets (BTC/ETH/TRX), etc.

> Heuristics are intentionally broad (recall > precision). Treat hits as **signals**, not proof. Review evidence (screenshots/HTML) before conclusions.

---

## 🗺️ Roadmap

- Still thingking what i should do next ? (if yo had any idea please tell me )

---

## ✅ Pros / ⚠️ Cons

**Pros**

- No API keys; works on the public web UI
- Evidence-friendly (screenshots/HTML) & exports for SOC workflows
- Multilingual heuristics (EN/ID shipped) with extensibility
- Flexible controls (locale, UA, proxy, modes)

**Cons**

- UI can change → selectors need maintenance
- Slower than official APIs; subject to rate limiting/bot checks
- Private/login-gated content is out-of-scope

---

## 🔐 Ethics & Legality

Use on **public information** only. Follow TikTok’s terms and laws in your jurisdiction. Intended for research, security awareness, and protective monitoring.

---

## 🤝 Contributing

PRs welcome! Improve selectors, add risk terms/languages, extend outputs, or wire up new pivots (e.g., by user mentions).

---

## 📄 License

MIT (suggested). Update this section if you prefer another license.
