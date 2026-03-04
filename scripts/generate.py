#!/usr/bin/env python3
import os
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from groq import Groq

GROQ_KEY      = os.environ["GROQ_API_KEY"]
ALPHA_VANTAGE = os.environ.get("ALPHA_VANTAGE_KEY", "")
BASE_REPORT_URL = "https://raw.githubusercontent.com/mikolaj-sz/mideast-monitor/main/base_report.html"

FEEDS = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.reuters.com/reuters/topNews",
    "https://www.theguardian.com/world/middleeast/rss",
]

KEYWORDS = [
    "iran", "israel", "middle east", "hormuz", "hezbollah",
    "tehran", "gaza", "lebanon", "houthi", "irgc", "khamenei",
    "nuclear", "oil", "crude", "brent", "wti", "strait",
    "missile", "strike", "attack", "war", "sanctions"
]

def fetch_base_report():
    try:
        req = urllib.request.Request(BASE_REPORT_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="ignore")
        # Strip HTML tags, keep text
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        # Keep first 6000 chars — most important context
        print(f"Base report: {len(text)} chars, using first 6000")
        return text[:6000]
    except Exception as e:
        print(f"Base report error: {e}")
        return ""

def fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read().decode("utf-8", errors="ignore")
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", content)
        descs  = re.findall(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", content)
        links  = re.findall(r"<link>(.*?)</link>", content)
        titles = [a or b for a, b in titles]
        descs  = [a or b for a, b in descs]
        links  = [l for l in links if l.startswith("http")][1:]
        result = []
        for i, (title, desc) in enumerate(zip(titles[1:], descs[1:])):
            link = links[i] if i < len(links) else ""
            result.append((title, desc, link))
        return result
    except Exception as e:
        print(f"RSS error {url}: {e}")
        return []

def collect_news():
    all_items = []
    for feed in FEEDS:
        all_items.extend(fetch_rss(feed))
    relevant = []
    seen = set()
    for title, desc, link in all_items:
        text = (title + " " + desc).lower()
        if any(kw in text for kw in KEYWORDS):
            key = title.strip()[:60]
            if key not in seen:
                seen.add(key)
                clean = re.sub(r"<[^>]+>", "", desc).strip()[:200]
                relevant.append({"title": title.strip(), "desc": clean, "url": link})
    return relevant[:40]

def fetch_gdelt():
    try:
        query = urllib.parse.quote("Iran Israel war Hormuz")
        url = f"https://api.gdeltproject.org/api/v2/doc/doc?query={query}&mode=artlist&maxrecords=10&format=json&timespan=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        items = []
        for a in data.get("articles", [])[:10]:
            title = a.get("title", "")
            if title:
                items.append({"title": f"[{a.get('domain','')}] {title}", "desc": "", "url": a.get("url","")})
        print(f"GDELT: {len(items)} articles")
        return items
    except Exception as e:
        print(f"GDELT error: {e}")
        return []

def fetch_oil_prices():
    if not ALPHA_VANTAGE:
        return {"brent": "N/A", "wti": "N/A"}
    try:
        with urllib.request.urlopen(f"https://www.alphavantage.co/query?function=WTI&interval=daily&apikey={ALPHA_VANTAGE}", timeout=10) as r:
            wti_price = json.loads(r.read()).get("data", [{}])[0].get("value", "N/A")
        with urllib.request.urlopen(f"https://www.alphavantage.co/query?function=BRENT&interval=daily&apikey={ALPHA_VANTAGE}", timeout=10) as r:
            brent_price = json.loads(r.read()).get("data", [{}])[0].get("value", "N/A")
        print(f"Oil: Brent ${brent_price}, WTI ${wti_price}")
        return {
            "brent": f"${brent_price}/bbl" if brent_price != "N/A" else "N/A",
            "wti":   f"${wti_price}/bbl"   if wti_price   != "N/A" else "N/A",
        }
    except Exception as e:
        print(f"Oil error: {e}")
        return {"brent": "N/A", "wti": "N/A"}

def fetch_analysis(base_report, news_items, gdelt_items, oil_prices):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    all_news = news_items + gdelt_items
    news_text = "\n".join([f"• {n['title']} — {n['desc']}" for n in all_news]) if all_news else "Brak nowych newsów."
    brent_live = oil_prices.get("brent", "N/A")
    wti_live   = oil_prices.get("wti",   "N/A")

    prompt = f"""Jesteś analitykiem geopolitycznym. Dziś jest {today}.
Aktualne ceny ropy: Brent {brent_live}, WTI {wti_live}

RAPORT BAZOWY (poprzednia aktualizacja — traktuj jako punkt wyjścia):
{base_report}

NAJNOWSZE NEWSY Z OSTATNICH GODZIN (RSS + GDELT):
{news_text}

Na podstawie raportu bazowego ORAZ najnowszych newsów wygeneruj zaktualizowany raport.
Zachowaj ciągłość z raportem bazowym, uwzględnij nowe zdarzenia z newsów.
Bądź konkretny — podawaj fakty, liczby, nazwy.

Zwróć WYŁĄCZNIE czysty JSON (bez markdown, bez backtick-ów):
{{
  "day_number": <liczba dni od 28 lutego 2026>,
  "headline": "Konkretny nagłówek najważniejszego nowego zdarzenia",
  "executive_summary": "2-3 zdania streszczenia aktualnej sytuacji z faktami",
  "key_stats": [
    {{"label": "Ofiary w Iranie", "value": "700+", "trend": "up"}},
    {{"label": "Brent Crude", "value": "{brent_live}", "trend": "up"}},
    {{"label": "Loty odwołane", "value": "1900+/dzień", "trend": "up"}},
    {{"label": "Bazy USA zaatakowane", "value": "27", "trend": "neutral"}},
    {{"label": "Statki zablokowane", "value": "150+", "trend": "up"}},
    {{"label": "Dzień konfliktu", "value": "5", "trend": "neutral"}}
  ],
  "timeline_today": [
    {{"time": "06:00 UTC", "title": "...", "detail": "szczegółowy opis", "is_new": true}},
    {{"time": "10:00 UTC", "title": "...", "detail": "szczegółowy opis", "is_new": true}},
    {{"time": "14:00 UTC", "title": "...", "detail": "szczegółowy opis", "is_new": true}},
    {{"time": "18:00 UTC", "title": "...", "detail": "szczegółowy opis", "is_new": false}}
  ],
  "actors": [
    {{"name": "USA", "status": "active", "summary": "..."}},
    {{"name": "Izrael", "status": "escalating", "summary": "..."}},
    {{"name": "Iran/IRGC", "status": "active", "summary": "..."}},
    {{"name": "Hezbollah", "status": "escalating", "summary": "..."}},
    {{"name": "Arabia Saudyjska", "status": "passive", "summary": "..."}},
    {{"name": "Rosja/Chiny", "status": "passive", "summary": "..."}}
  ],
  "risks": [
    {{"name": "Zamknięcie Cieśniny Ormuz", "probability": "aktywne", "impact": "krytyczny", "status_change": "bez zmian"}},
    {{"name": "Front libański – Hezbollah", "probability": "aktywne", "impact": "wysoki", "status_change": "wzrost"}},
    {{"name": "Szok naftowy Brent $100+", "probability": "wysokie", "impact": "krytyczny", "status_change": "wzrost"}},
    {{"name": "Próżnia władzy w Iranie", "probability": "wysokie", "impact": "krytyczny", "status_change": "bez zmian"}},
    {{"name": "Starcie morskie USA-Iran", "probability": "średnie", "impact": "krytyczny", "status_change": "nowe"}},
    {{"name": "Ataki na infrastrukturę Aramco", "probability": "wysokie", "impact": "krytyczny", "status_change": "wzrost"}}
  ],
  "scenarios": [
    {{"label": "A. Szybka deeskalacja", "probability_label": "Niskie (10-15%)", "description": "Trump ogłasza sukces, Iran wyłania umiarkowanego przywódcę, Ormuz otwiera się."}},
    {{"label": "B. Konflikt 4-5 tygodni", "probability_label": "Najwyższe (60-65%)", "description": "Systematyczne uderzenia, blokada Ormuz, Brent $90-100, dyplomacja po wyczerpaniu."}},
    {{"label": "C. Starcie morskie w Ormuz", "probability_label": "Rosnące (15-20%)", "description": "Iran atakuje konwoje US Navy, bezpośrednie starcie morskie, ryzyko wciągnięcia Chin."}},
    {{"label": "D. Implozja Iranu", "probability_label": "Niskie (5-10%)", "description": "Protesty przeradzają się w rewolucję, IRGC zachowuje strukturę, brak demokratycznej opozycji."}}
  ],
  "energy_markets": {{
    "brent": "{brent_live}",
    "wti": "{wti_live}",
    "hormuz_status": "Zamknięta od 2 marca",
    "lng_europe": "+20% (niedobory)"
  }},
  "sources_used": ["BBC", "Al Jazeera", "Reuters", "NYT", "Guardian", "GDELT", "Alpha Vantage"],
  "alert_level": "krytyczny",
  "alert_message": "Cieśnina Ormuz zamknięta — 20% globalnych dostaw ropy zagrożone"
}}"""

    print(f"Sending to Groq ({len(all_news)} news + base report)...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4000,
        temperature=0.3,
    )
    text = response.choices[0].message.content.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)

def render_html(data, oil_prices, news_items, gdelt_items):
    now_utc       = datetime.now(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    day_num       = data.get("day_number", "?")
    headline      = data.get("headline", "Analiza Bliskiego Wschodu")
    summary       = data.get("executive_summary", "")
    alert_level   = data.get("alert_level", "wysoki")
    alert_message = data.get("alert_message", "")

    alert_colors = {
        "krytyczny":   ("#c0392b", "#fdf0f0"),
        "wysoki":      ("#d35400", "#fdf3e3"),
        "podwyższony": ("#b7950b", "#fefaed"),
        "normalny":    ("#1e8449", "#eafaf1"),
    }
    alert_accent, alert_bg = alert_colors.get(alert_level, ("#c0392b", "#fdf0f0"))

    stats_html = ""
    for s in data.get("key_stats", []):
        trend = s.get("trend", "neutral")
        arrow = {"up": "▲", "down": "▼", "neutral": "●"}.get(trend, "●")
        color = {"up": "#c0392b", "down": "#1e8449", "neutral": "#7f8c8d"}.get(trend, "#7f8c8d")
        stats_html += f'<div class="stat-card"><div class="stat-value">{s.get("value","–")}</div><div class="stat-label">{s.get("label","")}</div><div class="stat-arrow" style="color:{color}">{arrow}</div></div>'

    timeline_html = ""
    for item in data.get("timeline_today", []):
        new_tag = '<span class="new-tag">NOWE</span>' if item.get("is_new") else ""
        timeline_html += f'<div class="tl-item"><div class="tl-time">{item.get("time","")}</div><div class="tl-body"><div class="tl-title">{item.get("title","")} {new_tag}</div><div class="tl-detail">{item.get("detail","")}</div></div></div>'

    status_color = {"active":"#c0392b","escalating":"#d35400","passive":"#7f8c8d","de-escalating":"#1e8449"}
    actors_html = ""
    for a in data.get("actors", []):
        color = status_color.get(a.get("status","passive"), "#7f8c8d")
        actors_html += f'<div class="actor-card"><div class="actor-header"><span class="actor-name">{a.get("name","")}</span><span class="actor-status" style="color:{color}">⬤ {a.get("status","").upper()}</span></div><div class="actor-summary">{a.get("summary","")}</div></div>'

    risk_badge = {
        "aktywne": ("AKTYWNE","#2c0a0a","#e74c3c"),
        "wysokie": ("WYSOKIE","#fde8e8","#922b21"),
        "średnie": ("ŚREDNIE","#fef9e7","#9a7d0a"),
        "niskie":  ("NISKIE", "#eafaf1","#1e8449"),
    }
    change_icon = {"nowe":"🆕","wzrost":"⬆️","bez zmian":"➡️","spadek":"⬇️"}
    risks_html = ""
    for r in data.get("risks", []):
        label, bg, fg = risk_badge.get(r.get("probability",""), ("?","#eee","#333"))
        icon = change_icon.get(r.get("status_change",""), "")
        risks_html += f'<tr><td>{r.get("name","")}</td><td><span class="badge" style="background:{bg};color:{fg}">{label}</span></td><td>{r.get("impact","")}</td><td>{icon} {r.get("status_change","")}</td></tr>'

    scenarios_html = ""
    for sc in data.get("scenarios", []):
        scenarios_html += f'<div class="scenario-card"><div class="sc-label">{sc.get("label","")}</div><div class="sc-prob">{sc.get("probability_label","")}</div><div class="sc-desc">{sc.get("description","")}</div></div>'

    em = data.get("energy_markets", {})
    energy_html = f'''<div class="energy-grid">
      <div class="en-item"><div class="en-val">{em.get("brent","–")}</div><div class="en-lbl">Brent Crude</div></div>
      <div class="en-item"><div class="en-val">{em.get("wti","–")}</div><div class="en-lbl">WTI Crude</div></div>
      <div class="en-item"><div class="en-val">{em.get("hormuz_status","–")}</div><div class="en-lbl">Cieśnina Ormuz</div></div>
      <div class="en-item"><div class="en-val">{em.get("lng_europe","–")}</div><div class="en-lbl">LNG Europa</div></div>
    </div>'''

    all_news = news_items + gdelt_items
    news_links_html = ""
    for n in all_news[:25]:
        url = n.get("url", "")
        title = n.get("title", "")
        desc = n.get("desc", "")
        if url and title:
            news_links_html += f'<div class="news-item"><a href="{url}" target="_blank" rel="noopener">{title}</a>{"<div class=news-desc>" + desc + "</div>" if desc else ""}</div>'

    sources_html = " ".join(f"<span>{s}</span>" for s in data.get("sources_used", []))

    return f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="18000">
<title>Monitor Bliskiego Wschodu – Dzień {day_num}</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f4f4f0;--surface:#ffffff;--border:#e2e2dc;--accent:#c0392b;--accent2:#d35400;--text:#1a1a1a;--muted:#6b7280;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-size:15px;line-height:1.7;}}
header{{border-bottom:1px solid var(--border);padding:0 48px;display:flex;align-items:center;justify-content:space-between;height:64px;position:sticky;top:0;z-index:100;background:rgba(255,255,255,0.97);backdrop-filter:blur(12px);box-shadow:0 1px 4px rgba(0,0,0,0.07);}}
.logo{{font-family:'Syne',sans-serif;font-weight:800;font-size:15px;letter-spacing:3px;text-transform:uppercase;color:var(--accent);}}
.header-right{{display:flex;align-items:center;gap:20px;}}
.header-meta{{font-size:12px;color:var(--muted);}}
.live-pill{{display:flex;align-items:center;gap:6px;background:#fdf0f0;border:1px solid #f5c6c6;border-radius:20px;padding:4px 12px;font-size:11px;font-weight:600;color:var(--accent);font-family:'Syne',sans-serif;letter-spacing:1px;}}
.live-dot{{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:blink 1.4s infinite;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
.hero{{padding:64px 48px 40px;max-width:1200px;margin:0 auto;display:grid;grid-template-columns:1fr 340px;gap:56px;align-items:start;}}
.day-label{{font-size:11px;letter-spacing:4px;text-transform:uppercase;color:var(--accent);font-family:'Syne',sans-serif;margin-bottom:16px;}}
.hero-headline{{font-family:'Syne',sans-serif;font-size:clamp(28px,4vw,46px);font-weight:800;line-height:1.12;margin-bottom:20px;color:var(--text);}}
.hero-summary{{font-size:16px;color:#4b5563;font-weight:300;line-height:1.85;margin-bottom:24px;border-left:3px solid var(--border);padding-left:16px;}}
.alert-box{{border-radius:8px;padding:14px 18px;border-left:4px solid {alert_accent};background:{alert_bg};margin-bottom:24px;}}
.al-level{{font-size:10px;letter-spacing:2px;text-transform:uppercase;font-family:'Syne',sans-serif;font-weight:700;color:{alert_accent};margin-bottom:4px;}}
.al-msg{{font-size:14px;color:var(--text);font-weight:500;}}
.stats-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px 16px;position:relative;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);}}
.stat-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:3px;background:var(--accent);}}
.stat-value{{font-family:'Syne',sans-serif;font-size:21px;font-weight:800;color:var(--text);}}
.stat-label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;margin-top:4px;line-height:1.3;}}
.stat-arrow{{position:absolute;top:14px;right:12px;font-size:13px;}}
.energy-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}}
.en-item{{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:16px;text-align:center;}}
.en-val{{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;color:var(--accent2);line-height:1.3;}}
.en-lbl{{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-top:5px;}}
.main{{max-width:1200px;margin:0 auto;padding:0 48px 80px;display:grid;grid-template-columns:1fr 340px;gap:28px;}}
.col-left>*+*,.col-right>*+*{{margin-top:24px;}}
.section{{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);}}
.section-head{{padding:14px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;background:#fafaf8;}}
.section-head h2{{font-family:'Syne',sans-serif;font-size:11px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--text);}}
.sh-accent{{width:3px;height:16px;background:var(--accent);border-radius:2px;flex-shrink:0;}}
.section-body{{padding:18px 22px;}}
.tl-item{{display:flex;gap:16px;padding:12px 0;border-bottom:1px solid var(--border);}}
.tl-item:last-child{{border:none;}}
.tl-time{{flex-shrink:0;width:80px;font-size:11px;font-weight:600;color:var(--accent);font-family:'Syne',sans-serif;padding-top:2px;}}
.tl-title{{font-size:14px;font-weight:500;margin-bottom:4px;color:var(--text);}}
.tl-detail{{font-size:13px;color:var(--muted);line-height:1.65;}}
.new-tag{{background:var(--accent);color:white;font-size:9px;font-weight:700;letter-spacing:1px;padding:1px 7px;border-radius:4px;margin-left:7px;vertical-align:middle;font-family:'Syne',sans-serif;}}
.actor-card{{padding:13px 0;border-bottom:1px solid var(--border);}}
.actor-card:last-child{{border:none;}}
.actor-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;}}
.actor-name{{font-family:'Syne',sans-serif;font-size:14px;font-weight:700;color:var(--text);}}
.actor-status{{font-size:10px;letter-spacing:1px;font-family:'Syne',sans-serif;font-weight:700;}}
.actor-summary{{font-size:13px;color:var(--muted);line-height:1.65;}}
.risk-table{{width:100%;border-collapse:collapse;font-size:13px;}}
.risk-table th{{text-align:left;padding:9px 10px;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);background:#fafaf8;font-weight:500;}}
.risk-table td{{padding:10px;border-bottom:1px solid var(--border);color:var(--text);vertical-align:top;}}
.risk-table tr:last-child td{{border:none;}}
.risk-table tr:hover td{{background:#fafaf8;}}
.badge{{display:inline-block;padding:2px 10px;border-radius:20px;font-size:10px;font-weight:700;letter-spacing:.5px;font-family:'Syne',sans-serif;}}
.scenario-card{{padding:16px;background:var(--bg);border:1px solid var(--border);border-radius:8px;margin-bottom:10px;}}
.scenario-card:last-child{{margin:0;}}
.sc-label{{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:var(--text);margin-bottom:4px;}}
.sc-prob{{font-size:11px;color:var(--accent);font-weight:600;letter-spacing:.5px;margin-bottom:6px;}}
.sc-desc{{font-size:13px;color:var(--muted);line-height:1.65;}}
.news-item{{padding:10px 0;border-bottom:1px solid var(--border);}}
.news-item:last-child{{border:none;}}
.news-item a{{font-size:13px;font-weight:500;color:var(--accent);text-decoration:none;line-height:1.5;display:block;}}
.news-item a:hover{{text-decoration:underline;color:#922b21;}}
.news-desc{{font-size:12px;color:var(--muted);margin-top:3px;line-height:1.5;}}
.sources-strip{{padding:14px 22px;font-size:11px;color:var(--muted);line-height:2.2;}}
.sources-strip span{{display:inline-block;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:2px 9px;margin:2px;}}
footer{{border-top:1px solid var(--border);padding:28px 48px;text-align:center;font-size:12px;color:var(--muted);background:var(--surface);}}
@media(max-width:900px){{
  header{{padding:0 20px;}}
  .hero{{grid-template-columns:1fr;padding:40px 20px 24px;gap:24px;}}
  .main{{grid-template-columns:1fr;padding:0 20px 60px;}}
}}
</style>
</head>
<body>
<header>
  <div class="logo">⬡ Bliski Wschód Monitor</div>
  <div class="header-right">
    <div class="header-meta">Aktualizacja: {now_utc}</div>
    <div class="live-pill"><div class="live-dot"></div>LIVE</div>
  </div>
</header>
<div class="hero">
  <div>
    <div class="day-label">Dzień {day_num} konfliktu · Baza HTML + RSS + GDELT + Alpha Vantage + Groq AI</div>
    <h1 class="hero-headline">{headline}</h1>
    <p class="hero-summary">{summary}</p>
    <div class="alert-box">
      <div class="al-level">⚠ Alert: {alert_level.upper()}</div>
      <div class="al-msg">{alert_message}</div>
    </div>
    <div class="stats-strip">{stats_html}</div>
  </div>
  <div>
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Rynki Energetyczne</h2></div>
      <div class="section-body">{energy_html}</div>
    </div>
  </div>
</div>
<div class="main">
  <div class="col-left">
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Kronika dnia</h2></div>
      <div class="section-body">{timeline_html}</div>
    </div>
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Macierz Ryzyka</h2></div>
      <div class="section-body">
        <table class="risk-table">
          <thead><tr><th>Zagrożenie</th><th>Prawdop.</th><th>Skutki</th><th>Zmiana</th></tr></thead>
          <tbody>{risks_html}</tbody>
        </table>
      </div>
    </div>
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Artykuły źródłowe ({len(all_news)})</h2></div>
      <div class="section-body">{news_links_html}</div>
    </div>
  </div>
  <div class="col-right">
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Aktorzy</h2></div>
      <div class="section-body">{actors_html}</div>
    </div>
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Scenariusze</h2></div>
      <div class="section-body">{scenarios_html}</div>
    </div>
    <div class="section">
      <div class="section-head"><div class="sh-accent"></div><h2>Źródła danych</h2></div>
      <div class="sources-strip">{sources_html}</div>
    </div>
  </div>
</div>
<footer>⬡ Monitor Bliskiego Wschodu · Baza HTML + RSS + GDELT + Alpha Vantage + Groq AI · {now_utc}</footer>
</body>
</html>"""

def main():
    print("=== Middle East Monitor ===")
    print("Fetching base report...")
    base = fetch_base_report()
    print("Fetching RSS...")
    news = collect_news()
    print(f"RSS: {len(news)} items")
    gdelt = fetch_gdelt()
    oil = fetch_oil_prices()
    data = fetch_analysis(base, news, gdelt, oil)
    html = render_html(data, oil, news, gdelt)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ index.html written")
    with open("last_updated.txt", "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    print("✓ Done!")

if __name__ == "__main__":
    main()
