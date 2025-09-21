# CROT DALAM — TikTok OSINT (No‑API)

> **C**ollection & **R**econnaissance **O**f **T**ikTok — **D**iscovery, **A**nalysis, **L**ogging, **A**nd **M**onitoring

**CROT DALAM** is a Python CLI that performs **OSINT on TikTok without any API keys**. It drives a real Chromium browser (via Playwright) to search public TikTok pages by keyword, extracts video metadata, applies scam/phishing **risk heuristics** (EN/ID), and exports **JSONL + CSV** (optionally **screenshots** for evidence).

> ⚠️ For public OSINT only. Respect local laws and platform terms. Do not use on private data or accounts.

---

## ✨ Features
- **No API keys** – scrapes public search & video pages using Playwright
- **Keyword OSINT** – search multiple keywords in one run
- **Risk scoring** – heuristic match for scam/phishing/fake promo terms (EN & Bahasa Indonesia)
- **Evidence** – optional full‑page screenshots per video
- **Exports** – structured **JSONL** and **CSV** for downstream analysis
- **Controls** – headless/visible mode, locale, proxy, custom UA, per‑keyword caps

---

## 🧠 How it works (Flow)

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

### Sequence
```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant CLI as crot_dalam.py
    participant PW as Playwright Chromium
    participant T as TikTok (public)

    U->>CLI: search "phishing" "promo gratis" --limit 80
    CLI->>PW: launch headless context (locale, UA, proxy)
    PW->>T: GET /search?q=...
    T-->>PW: Search results page
    CLI->>PW: scroll & parse anchors (/video/...)
    loop For each video URL
        PW->>T: GET /@user/video/<id>
        T-->>PW: Video page
        CLI->>PW: extract JSON-LD, meta tags, DOM
        CLI->>CLI: risk_score(description)
        alt with --screenshot
            CLI->>PW: screenshot full page
        end
    end
    CLI-->>U: Save .jsonl, .csv + summary
```

**Risk Heuristics (examples)**
- EN: `scam`, `phishing`, `smishing`, `click link`, `free iphone`, `crypto giveaway`, `OTP`, `verification code`, `KYC`
- ID: `penipuan`, `modus`, `phising`, `klik link`, `tautan di bio`, `transfer dulu`, `deposit dulu`, `langsung cair`, `kode OTP`, `jangan kasih OTP`

---

## 🧰 Installation
```bash
# Python 3.10+
python -m pip install playwright typer rich
python -m playwright install chromium
```
> **Linux notes:** Playwright will fetch Chromium. If it complains about system libs, install common deps (e.g., `libnss3`, `libatk1.0-0`, `libx11` family) via your distro’s package manager.

---

## 🚀 Usage
**Basic search (headless)**
```bash
python crot_dalam.py search "phishing" "scam" --limit 80 --out out/crot_dalam
```

**Visible browser + Indonesian locale + screenshots**
```bash
python crot_dalam.py search "promo gratis" \
  --locale id-ID --headless false --screenshot --limit 40
```

**Per‑keyword cap** (distribute total among keywords or force a per‑keyword number)
```bash
# total limit shared across keywords (default behavior)
python crot_dalam.py search "phishing" "giveaway" --limit 100

# force per‑keyword cap of 60 (up to 120 total if two keywords)
python crot_dalam.py search "phishing" "giveaway" --per-keyword-limit 60 --limit 120
```

**Custom UA + Proxy**
```bash
python crot_dalam.py search "binary option" \
  --user-agent "Mozilla/5.0 ..." \
  --proxy http://user:pass@host:port \
  --limit 50
```

**Output**
```
out/
  ├─ crot_dalam.jsonl   # one JSON object per line
  ├─ crot_dalam.csv     # table with common fields
  └─ screenshots/       # optional PNGs (one per video)
```

---

## 📚 Libraries used
- **Playwright** – headless Chromium automation
- **Typer** – ergonomic CLI
- **Rich** – pretty console output
- Python stdlib: `json`, `csv`, `re`, `pathlib`, `urllib.parse`, etc.

---

## 🔎 Use cases
- **Threat intel & OSINT:** monitor trending scams, phishing campaigns, fake promos
- **Brand protection:** find imposters abusing brand names, fake giveaways, coupon scams
- **Financial fraud monitoring:** identify crypto/forex signal scams & Ponzi promos
- **Awareness & education:** collect real examples to brief stakeholders

---

## 🧪 Sample commands
```bash
# 1) Quick crawl, 80 items total
python crot_dalam.py search "phishing" "scam" --limit 80 --out out/crot

# 2) Evidence screenshots
python crot_dalam.py search "giveaway" --screenshot --limit 40

# 3) Bahasa keywords, visible mode
python crot_dalam.py search "promo gratis" "transfer dulu" --locale id-ID --headless false --limit 60

# 4) Proxy + custom UA
python crot_dalam.py search "binary option" --proxy http://127.0.0.1:8080 \
  --user-agent "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ..." --limit 30
```

---

## 🗺️ Roadmap
- [ ] **Entity extraction** (user mentions, tagged accounts, URLs in description)
- [ ] **Language detection** + per‑language risk terms
- [ ] **Config file** (YAML) for reusable runs & keyword sets
- [ ] **SQLite/Parquet backend** + dashboards (DuckDB/Polars)
- [ ] **Schedulers** (cron‑style pulls) + daily diffs
- [ ] **Rotating proxies & backoff** to handle rate limiting gracefully
- [ ] **Dockerfile** for reproducible deployments
- [ ] **Dedup & canonicalization** across reruns
- [ ] **Pivoting** (auto‑follow hashtags/users from hits)
- [ ] **Packaging** (pipx/pyproject) and single‑file binaries (PyInstaller)

---

## ✅ Pros / ⚠️ Cons
**Pros**
- No API keys; works only with public web UI
- Evidence‑friendly (screenshots) & exports for SOC workflows
- Multilingual heuristic risk matching (EN/ID included)
- Flexible controls (locale, UA, proxy)

**Cons**
- Web UI may change → selectors can break (maintenance needed)
- Slower than official APIs; subject to rate limiting / bot mitigation
- Login‑gated/private content is out of scope
- Counts/fields may be partial or delayed depending on page structure

---

## 🔐 Ethics & legality
Use on **public information** only. Follow TikTok’s terms and applicable laws in your jurisdiction. This tool is intended for research, security awareness, and protective monitoring.

---

## 🖼️ Banner (shown on start)
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

## 🤝 Contributing
Pull requests are welcome! Improve selectors, add languages to risk heuristics, extend outputs.

---

## 📄 License
MIT (suggested). If you prefer another license, update this section.
