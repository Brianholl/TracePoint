<div align="center">

# 🕵️ TracePoint

### Multi-Vector Intelligence Collection Platform

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat)](LICENSE)
[![OpenRouter](https://img.shields.io/badge/Powered%20by-OpenRouter-8A2BE2?style=flat)](https://openrouter.ai)
[![AI](https://img.shields.io/badge/AI-DeepSeek%20|%20Gemini%20|%20Claude-blue?style=flat)](#-ai-analysis-engine)
[![Platforms](https://img.shields.io/badge/Platforms-50+-brightgreen?style=flat)](#-username-intelligence)
[![Raspberry Pi](https://img.shields.io/badge/RPi-5%20Ready-c51a4a?style=flat&logo=raspberrypi)](https://raspberrypi.com)

**TracePoint** is a professional open-source intelligence collection platform designed to aggregate, correlate, and analyze publicly available information about a target from **50+ sources** — all from a clean web interface. Powered by **multi-model AI** via OpenRouter.

<img src="https://img.shields.io/badge/STATUS-ACTIVE-success?style=for-the-badge&logo=dependabot"/>

---

[Features](#-features) • [Architecture](#-architecture) • [Quick Start](#-quick-start) • [Modules](#-modules) • [AI Engine](#-ai-analysis-engine) • [Deploy](#-deployment) • [Roadmap](#-roadmap)

</div>

---

## 📋 Features

<table>
<tr>
<td width="50%">

### 🔍 Username Intelligence
- Scan **50+ platforms** simultaneously
- GitHub, Instagram, Twitter/X, Reddit, TikTok, YouTube, Telegram, Facebook, LinkedIn, and more
- **Smart verification**: detects real profiles vs. placeholder/error pages
- Unverified results clearly marked

</td>
<td width="50%">

### 📧 Email Intelligence
- **HIBP** breach detection
- **Gravatar** profile extraction
- **Holehe** — 20+ site registration check
- **Google dorking** — automated leak hunting

</td>
</tr>
<tr>
<td width="50%">

### 👤 Identity Resolution
- **Name** cross-reference across web and social media
- **Facebook** + **LinkedIn** scraping (cookie auth)
- **Google dorking** — documents, credentials, personal info

</td>
<td width="50%">

### 📱 Phone Analysis
- Carrier identification
- Geolocation & timezone mapping
- Web footprint across directories and dork results

</td>
</tr>
<tr>
<td width="50%">

### 🖼️ Photo Intelligence (NEW)
- **Reverse image search** via Google Lens, Yandex, Bing
- Automatic social profile detection from image results
- **Face-to-profile** matching across platforms
- Powered by **Gemini 3.5 Flash** vision model

</td>
<td width="50%">

### 🌐 Deep Web Scan
- Tor-based reconnaissance
- `.onion` site scanning
- Graceful fallback when Tor unavailable

</td>
</tr>
<tr>
<td width="50%">

### 🤖 AI Analysis Engine
- **3-tier model routing**:
  - 📝 Text → **DeepSeek V4 Flash** (free)
  - 🖼️ Text+Image → **Gemini 3.5 Flash** (vision)
  - 📊 Extreme volume → **Claude Opus 4.7**
- Cross-reference correlation
- Risk assessment & confidence scoring

</td>
<td width="50%">

### 📄 Professional Reports
- **A4 print-optimized** B&W intelligence documents
- Styled after intelligence agency formats
- One-click PDF via browser print
- Markdown AI analysis rendering

</td>
</tr>
</table>

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Web UI (FastAPI)                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │
│  │ Dashboard│ │DeepSearch│ │  Search  │ │  History/Logs │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬───────┘  │
│       │            │            │               │          │
│  ┌────┴────────────┴────────────┴───────────────┴───────┐  │
│  │               Async Task Orchestrator                 │  │
│  └────┬────────────┬────────────┬───────────────┬───────┘  │
│       │            │            │               │          │
│  ┌────┴────┐ ┌────┴────┐ ┌────┴────┐ ┌────────┴────────┐ │
│  │Username │ │  Email  │ │  Phone  │ │ Image→Social    │ │
│  │50+ plat │ │HIBP+Gra │ │Carrier+ │ │ Lens/Yandex/Bing│ │
│  │ +social │ │+Holehe  │ │ Geo+Dork│ │ +profile verify │ │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────────┬────────┘ │
│       │            │            │               │          │
│  ┌────┴────────────┴────────────┴───────────────┴───────┐  │
│  │              AI Correlation (OpenRouter)               │  │
│  │  DeepSeek ←─ Gemini ←─ Claude (auto-routed)           │  │
│  └───────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Report Generator (HTML/Print)             │  │
│  └───────────────────────────────────────────────────────┘  │
│                          │                                  │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │              SQLite Database (persistent)              │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- OpenRouter API key ([free credits available](https://openrouter.ai))
- Tor (optional, for deep web scanning)

### Installation

```bash
# Clone the repository
git clone https://github.com/zeba673/OSINT-WEB.git
cd OSINT-WEB

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your API key
cp .env.example .env
# Edit .env → add your OPENROUTER_API_KEY

# Run the server
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open **http://localhost:8000** in your browser.

### Docker (recommended)

```bash
docker build -t tracepoint .
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/.env:/app/.env \
  tracepoint
```

---

## 📦 Modules

| Module | Description |
|--------|-------------|
| `search_usernames.py` | 50+ platform scanner with smart false-positive detection |
| `search_email.py` | Gravatar + HIBP breach check + Google dorking |
| `search_name.py` | Web + social cross-reference for full names |
| `search_phone.py` | Carrier, geo, timezone, web footprint |
| `image_social_search.py` | Reverse image → social profile matching |
| `ai_analyzer.py` | Multi-model routing (DeepSeek/Gemini/Claude) |
| `social_instagram.py` | Instaloader-based Instagram scraper |
| `social_twitter.py` | Twitter API + Nitter fallback |
| `social_facebook.py` | Cookie-authenticated Facebook scraper |
| `social_linkedin.py` | li_at cookie LinkedIn search |
| `social_telegram.py` | Telethon-based Telegram search |
| `social_discord.py` | Discord user/guild/friend scraper |
| `holehe_checker.py` | 20+ site email registration check |
| `google_dorker.py` | Automated Google dork queries |
| `breach_checker.py` | Leak/paste search |
| `search_deepweb.py` | Tor-based .onion reconnaissance |
| `report_generator.py` | Professional A4 print-optimized reports |

---

## 🤖 AI Analysis Engine

TracePoint uses **intelligent model routing** via OpenRouter to optimize cost and capability:

| Input Type | Model | Cost | Capability |
|------------|-------|------|------------|
| 📝 Text only | `deepseek/deepseek-v4-flash` | **Free** | General OSINT correlation |
| 🖼️ Text + Image | `google/gemini-3.5-flash` | $0.10/M tok | Visual analysis + profile matching |
| 📊 Extreme volume (50+ profiles) | `anthropic/claude-opus-4.7` | $5/M tok | Deep multi-source correlation |

Configure in `.env`:
```env
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL_TEXT=deepseek/deepseek-v4-flash
OPENROUTER_MODEL_VISION=google/gemini-3.5-flash
OPENROUTER_MODEL_EXTREME=anthropic/claude-opus-4.7
```

---

## 🖥 Deployment

### Raspberry Pi 5 (recommended)

```bash
# Full guide available in the repo
docker compose up -d
```

### CasaOS

Install via CasaOS App Store as a custom Docker Compose application.

### Cloud VPS

```bash
docker run -d -p 80:8000 \
  -e VIRTUAL_HOST=osint.yourdomain.com \
  tracepoint
```

---

## 🗺 Roadmap

- [x] 50+ platform username scanner
- [x] Email breach detection (HIBP + Holehe)
- [x] Name and phone intelligence
- [x] Social media scraping (IG, Twitter/X, FB, LI, TG, Discord)
- [x] Photo reverse image search + face-to-profile
- [x] AI multi-model routing (DeepSeek/Gemini/Claude)
- [x] Professional print-optimized reports
- [x] Deep web Tor scanning
- [x] Dark/Light theme + EN/ES localization
- [ ] WebSocket real-time progress
- [ ] Playwright-based SPA scraping (Instagram, TikTok)
- [ ] Graph visualization of social connections
- [ ] Scheduled monitoring with alerts
- [ ] Plugin system for community modules

---

## ⚠️ Legal & Ethical

**TracePoint** is designed for:
- **Security researchers** conducting authorized assessments
- **Journalists** investigating public figures
- **Law enforcement** with proper legal authority
- **Individuals** researching their own digital footprint

**You are responsible** for complying with all applicable laws and platform Terms of Service. The authors assume no liability for misuse.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Made with 🧠 by [zeba673](https://github.com/zeba673)

**Collect intelligence responsibly.**

</div>
