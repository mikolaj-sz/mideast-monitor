#!/usr/bin/env python3
import os
import re
import json
import urllib.request
from datetime import datetime, timezone
from groq import Groq

FEEDS = [
    "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml",
    "https://rss.nytimes.com/services/xml/rss/nyt/MiddleEast.xml",
    "https://www.aljazeera.com/xml/rss/all.xml",
    "https://feeds.reuters.com/reuters/topNews",
]

KEYWORDS = [
    "iran", "israel", "middle east", "hormuz", "hezbollah",
    "tehran", "gaza", "lebanon", "houthi", "irgc", "khamenei",
    "nuclear", "oil", "crude", "bliski wschód"
]

def fetch_rss(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            content = r.read().decode("utf-8", errors="ignore")
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", content)
        descs  = re.findall(r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>", content)
        titles = [a or b for a, b in titles]
        descs  = [a or b for a, b in descs]
        return list(zip(titles[1:], descs[1:]))
    except Exception as e:
        print(f"RSS error {url}: {e}")
        return []

def collect_news():
    all_items = []
    for feed in FEEDS:
        all_items.extend(fetch_rss(feed))
    relevant = []
    seen = set()
    for title, desc in all_items:
        text = (title + " " + desc).lower()
        if any(kw in text for kw in KEYWORDS):
            key = title.strip()[:60]
            if key not in seen:
                seen.add(key)
                clean = re.sub(r"<[^>]+>", "", desc).strip()[:200]
                relevant.append(f"• {title.strip()} — {clean}")
    return relevant[:30]

def fetch_analysis(news_items):
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    news_text = "\n".join(news_items) if news_items else "Brak świeżych newsów."
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    prompt = f"""Jesteś analitykiem geopolitycznym. Na podstawie newsów z {today} wygeneruj raport o sytuacji na Bliskim Wschodzie.

NEWSY:
{news_text}

Zwróć WYŁĄCZNIE czysty JSON (bez markdown, bez backtick-ów):
{{
  "day_number": <liczba dni od 28 lutego 2026>,
  "headline": "Krótki nagłówek najważniejszego zdarzenia",
  "executive_summary": "2-3 zdania streszczenia sytuacji",
  "key_stats": [
    {{"label": "...", "value": "...", "trend": "up|down|neutral"}}
  ],
  "timeline_today": [
    {{"time": "Rano/Południe/Wieczór", "title": "...", "detail": "...", "is_new": true}}
  ],
  "actors": [
    {{"name": "...", "status": "active|passive|escalating|de-escalating", "summary": "..."}}
  ],
  "risks": [
    {{"name": "...", "probability": "aktywne|wysokie|średnie|niskie", "impact": "krytyczny|wysoki|średni", "status_change": "nowe|wzrost|bez zmian|spadek"}}
  ],
  "scenarios": [
    {{"label": "...", "probability_label": "...", "description": "..."}}
  ],
  "energy_markets": {{
    "brent": "...", "wti": "...", "hormuz_status": "...", "lng_europe": "..."
  }},
  "sources_used": ["BBC", "Al Jazeera", "Reuters", "NYT"],
  "alert_level": "krytyczny|wysoki|podwyższony|normalny",
  "alert_message": "Jedno zdanie opisujące główne zagrożenie"
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=3000,
        temperature=0.3,
    )
    text = response.choices[0].message.content.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)

def render_html(data):
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
    energy_html = f'<div class="energy-grid"><div class="en-item"><div class="en-val">{em.get("brent","–")}</div><div class="en-lbl">Brent Crude</div></div><div class="en-item"><div class="en-val">{em.get("wti","–")}</div><div class="en-lbl">WTI Crude</div></div><div class="en-item"><div class="en-val">{em.get("hormuz_status","–")}</div><div class="en-lbl">Cieśnina Ormuz</div></div><div class="en-item"><div class="en-val">{em.get("lng_europe","–")}</div><div class="en-lbl">LNG Europa</div></div></div>'

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
:root{{--bg:#f7f7f5;--surface:#ffffff;--border:#e5e5e0;--accent:#c0392b;--accent2:#d35400;--text:#1a1a1a;--muted:#6b7280;--header-bg:#ffffff;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',sans-serif;font-size:15px;line-height:1.7;}}
header{{border-bottom:1px solid var(--border);padding:0 48px;display:flex;align-items:center;justify-content:space-between;height:64px;position:sticky;top:0;z-index:100;background:rgba(255,255,255,0.96);backdrop-filter:blur(12px);box-shadow:0 1px 3px rgba(0,0,0,0.06);}}
.logo{{font-family:'Syne',sans-serif;font-weight:800;font-size:15px;letter-spacing:3px;text-transform:uppercase;color:var(--accent);}}
.header-meta{{font-size:12px;color:var(--muted);}}
.live-dot{{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--accent);margin-right:6px;animation:blink 1.4s infinite;}}
@keyframes blink{{0%,100%{{opacity:1}}50%{{opacity:.2}}}}
.hero{{padding:64px 48px 40px;max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1fr 320px;gap:48px;align-items:start;}}
.day-label{{font-size:11px;letter-spacing:4px;text-transform:uppercase;color:var(--accent);font-family:'Syne',sans-serif;margin-bottom:16px;}}
.hero-headline{{font-family:'Syne',sans-serif;font-size:clamp(26px,4vw,42px);font-weight:800;line-height:1.15;margin-bottom:20px;color:var(--text);}}
.hero-summary{{font-size:16px;color:#4b5563;font-weight:300;line-height:1.8;margin-bottom:24px;}}
.alert-box{{border-radius:8px;padding:14px 18px;border-left:3px solid {alert_accent};background:{alert_bg};margin-bottom:20px;}}
.al-level{{font-size:10px;letter-spacing:2px;text-transform:uppercase;font-family:'Syne',sans-serif;font-weight:700;color:{alert_accent};margin-bottom:4px;}}
.al-msg{{font-size:14px;color:var(--text);}}
.stats-strip{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;}}
.stat-card{{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:18px;position:relative;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);}}
.stat-card::before{{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--accent);}}
.stat-value{{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;color:var(--text);}}
.stat-label{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-top:4px;}}
.stat-arrow{{position:absolute;top:14px;right:14px;font-size:14px;}}
.energy-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;}}
.en-item{{background:var(--bg);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center;}}
.en-val{{font-family:'Syne',sans-serif;font-size:17px;font-weight:700;color:var(--accent2);}}
.en-lbl{{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-top:4px;}}
.main{{max-width:1100px;margin:0 auto;padding:0 48px 80px;display:grid;grid-template-columns:1fr 320px;gap:28px;}}
.col-left>*+*,.col-right>*+*{{margin-top:24px;}}
.section{{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.04);}}
.section-head{{padding:14px 22px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;background:#fafaf8;}}
.section-head h2{{font-family:'Syne',sans-serif;font-size:12px;font-weight:700;letter-spacing:2px;text-transform:uppercase;color:var(--text);}}
.sh-accent{{width:4px;height:16px;background:var(--accent);border-radius:2px;flex-shrink:0;}}
.section-body{{padding:18px 22px;}}
.tl-item{{display:flex;gap:14px;padding:11px 0;border-bottom:1px solid var(--border);}}
.tl-item:last-child{{border:none;}}
.tl-time{{flex-shrink:0;width:75px;font-size:11px;font-weight:600;color:var(--accent);font-family:'Syne',sans-serif;padding-top:2px;}}
.tl-title{{font-size:14px;font-weight:500;margin-bottom:3px;color:var(--text);}}
.tl-detail{{font-size:13px;color:var(--muted);line-height:1.6;}}
.new-tag{{background:var(--accent);color:white;font-size:9px;font-weight:700;letter-spacing:1px;padding:1px 6px;border-radius:4px;margin-left:6px;vertical-align:middle;}}
.actor-card{{padding:12px 0;border-bottom:1px solid var(--border);}}
.actor-card:last-child{{border:none;}}
.actor-header{{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;}}
.actor-name{{font-family:'Syne',sans-serif;font-size:14px;font-weight:700;color:var(--text);}}
.actor-status{{font-size:10px;letter-spacing:1px;font-family:'Syne',sans-serif;font-weight:700;}}
.actor-summary{{font-size:13px;color:var(--muted);line-height:1.6;}}
.risk-table{{width:100%;border-collapse:collapse;font-size:13px;}}
.risk-table th{{text-align:left;padding:8px 10px;font-size:10px;letter-spacing:1px;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--border);background:#fafaf8;}}
.risk-table td{{padding:9px 10px;border-bottom:1px solid var(--border);color:var(--text);}}
.risk-table tr:last-child td{{border:none;}}
.badge{{display:inline-block;padding:2px 9px;border-radius:10px;font-size:10px;font-weight:700;letter-spacing:.5px;}}
.scenario-card{{padding:14px;background:var(--bg);border:1px solid var(--border);border-radius:8px;margin-bottom:10px;}}
.scenario-card:last-child{{margin:0;}}
.sc-label{{font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:var(--text);margin-bottom:3px;}}
.sc-prob{{font-size:11px;color:var(--accent);font-weight:600;letter-spacing:.5px;margin-bottom:5px;}}
.sc-desc{{font-size:13px;color:var(--muted);line-height:1.6;}}
.sources-strip{{padding:14px 22px;font-size:11px;color:var(--muted);line-height:2;}}
.sources-strip span{{display:inline-block;background:var(--bg);border:1px solid var(--border);border-radius:4px;padding:1px 8px;margin:2px;}}
footer{{border-top:1px solid var(--border);padding:24px 48px;text-align:center;font-size:12px;color:var(--muted);background:var(--surface);}}
@media(max-width:800px){{header{{padding:0 20px;}}.hero{{grid-template-columns:1fr;padding:40px 20px 24px;gap:20px;}}.main{{grid-template-columns:1fr;padding:0 20px 60px;}}}}
</style>
</head>
<body>
<header>
  <div class="logo">⬡ Bliski Wschód Monitor</div>
  <div class="header-meta"><span class="live-dot"></span>Aktualizacja: {now_utc} · Auto-odświeżanie co 5h</div>
</header>
<div class="hero">
  <div>
    <div class="day-label">Dzień {day_num} konfliktu · Raport automatyczny</div>
    <h1 class="hero-headline">{headline}</h1>
    <p class="hero-summary">{summary}</p>
    <div class="alert-box"><div class="al-level">Alert: {alert_level.upper()}</div><div class="al-msg">{alert_message}</div></div>
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
          <thead><tr><th>Zagrożenie</th><th>Prawdopodobieństwo</th><th>Skutki</th><th>Zmiana</th></tr></thead>
          <tbody>{risks_html}</tbody>
        </table>
      </div>
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
      <div class="section-head"><div class="sh-accent"></div><h2>Źródła</h2></div>
      <div class="sources-strip">{sources_html}</div>
    </div>
  </div>
</div>
<footer>⬡ Monitor Bliskiego Wschodu · RSS + Groq AI · {now_utc}</footer>
</body>
</html>"""

def main():
    print("Fetching RSS feeds...")
    news = collect_news()
    print(f"Found {len(news)} relevant items")
    data = fetch_analysis(news)
    html = render_html(data)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("✓ index.html written")
    with open("last_updated.txt", "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    print("✓ last_updated.txt written")

if __name__ == "__main__":
    main()
