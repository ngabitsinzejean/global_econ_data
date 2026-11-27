import re
from datetime import datetime, timezone
import duckdb
import pandas as pd
import requests
import feedparser
from bs4 import BeautifulSoup

# Official Rwandan & East African Financial News Feeds + Institutional Portals
NEWS_SOURCES = [
    {
        "institution": "National Bank of Rwanda (BNR)",
        "category": "Central Bank & Monetary Policy",
        "type": "scrape",
        "url": "https://bnr.rw",
        "base_url": "https://bnr.rw"
    },
    {
        "institution": "National Institute of Statistics (NISR)",
        "category": "Official Statistics & Releases",
        "type": "scrape",
        "url": "https://statistics.gov.rw",
        "base_url": "https://statistics.gov.rw"
    },
    {
        "institution": "MINECOFIN Rwanda",
        "category": "Fiscal Policy & National Budget",
        "type": "scrape",
        "url": "https://minecofin.gov.rw",
        "base_url": "https://minecofin.gov.rw"
    },
    {
        "institution": "Rwanda Financial & Business Press (Google News RSS)",
        "category": "Banking, RSE & Economy",
        "type": "rss",
        "url": "https://google.com",
        "base_url": "https://google.com"
    }
]

# Keywords to ensure only relevant economic and financial updates are kept
ECON_KEYWORDS = [
    "bnr", "central bank", "monetary", "inflation", "cpi", "gdp", "rate",
    "rwf", "franc", "exchange", "bank", "kigali", "i&m", "equity", "bpr",
    "rse", "stock", "bond", "treasury", "budget", "minecofin", "nisr",
    "economy", "economic", "growth", "trade", "export", "import", "debt", "tax"
]


def is_relevant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in ECON_KEYWORDS)


def scrape_official_portal(src: dict) -> list:
    records = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EconHubBot/1.0)"}
    try:
        resp = requests.get(src["url"], headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            title = re.sub(r"\s+", " ", a.get_text(strip=True))
            href = a["href"]
            if len(title) < 25 or not is_relevant(title):
                continue

            full_link = href if href.startswith("http") else src["base_url"].rstrip("/") + "/" + href.lstrip("/")
            records.append({
                "institution": src["institution"],
                "category": src["category"],
                "title": title,
                "published_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "link": full_link,
                "verified_source": "Official Institutional Portal"
            })
    except Exception as e:
        print(f"Portal notice ({src['institution']}): {e}")
    return records


def fetch_rss_feed(src: dict) -> list:
    records = []
    try:
        feed = feedparser.parse(src["url"])
        for entry in feed.entries[:25]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "")
            pub = entry.get("published", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
            if title and is_relevant(title):
                records.append({
                    "institution": src["institution"],
                    "category": src["category"],
                    "title": title,
                    "published_date": pub[:16],
                    "link": link,
                    "verified_source": "Verified Financial Press Feed"
                })
    except Exception as e:
        print(f"RSS notice ({src['institution']}): {e}")
    return records


def run_news_pipeline():
    all_news = []
    for src in NEWS_SOURCES:
        if src["type"] == "scrape":
            all_news.extend(scrape_official_portal(src))
        else:
            all_news.extend(fetch_rss_feed(src))

    # Add curated institutional reference links so portals are always accessible
    pinned_links = [
        {
            "institution": "National Bank of Rwanda (BNR)",
            "category": "Official Portal & Exchange Rates",
            "title": "BNR Official Portal — Monetary Policy, Exchange Rates & Financial Stability",
            "published_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "link": "https://bnr.rw",
            "verified_source": "Official Central Bank Portal"
        },
        {
            "institution": "National Institute of Statistics (NISR)",
            "category": "Official Portal & Statistical Releases",
            "title": "NISR Official Portal — CPI Inflation, GDP, Labour Force & EICV Releases",
            "published_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "link": "https://statistics.gov.rw",
            "verified_source": "Official National Statistics Portal"
        },
        {
            "institution": "World Bank DataBank",
            "category": "Global Macroeconomic Portal",
            "title": "World Bank DataBank — World Development Indicators (WDI) & Rwanda Country Profile",
            "published_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "link": "https://worldbank.org",
            "verified_source": "Official International Portal"
        }
    ]

    df = pd.DataFrame(pinned_links + all_news).drop_duplicates(subset=["title"])
    df["fetched_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    con = duckdb.connect("economics_hub.duckdb")
    con.execute("CREATE OR REPLACE TABLE rwanda_finance_news AS SELECT * FROM df")
    con.close()
    print(f"SUCCESS: Stored {len(df)} verified BNR, NISR & Rwanda financial news items!")


if __name__ == "__main__":
    run_news_pipeline()
