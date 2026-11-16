"""
ML&R Lead Scraper v4 — Small Business Lead Generator
Nationwide. Phone numbers, addresses, website status.

BEST RESULTS: Use the Google Places API (free tier).
  $env:GOOGLE_API_KEY = "your_key_here"
  python lead_scraper.py --preset lawyers --location "Dallas, TX" --api

FREE (limited): DuckDuckGo + Bing search scraping.
  python lead_scraper.py --preset salons --location "Phoenix, AZ"

Usage:
  python lead_scraper.py --preset lawyers --location "Minneapolis, MN"
  python lead_scraper.py --category "nail salon" --location "Dallas, TX" --limit 30
  python lead_scraper.py --preset salons --location "Phoenix, AZ" --api
  python lead_scraper.py --preset lawyers --location "Chicago, IL" --output chicago_lawyers
"""

import argparse, csv, json, os, random, re, sys, time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass
from urllib.parse import quote_plus

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "beautifulsoup4"])
    import requests
    from bs4 import BeautifulSoup


PRESETS = {
    "creatives": {
        "q": ["wedding photographer","portrait photographer","photography studio",
              "family photographer","tattoo shop","tattoo parlor","dog groomer","florist"]
    },
    "lawyers": {
        "q": ["criminal defense lawyer","personal injury attorney","dui lawyer",
              "family law attorney","divorce lawyer","bankruptcy attorney","immigration lawyer"]
    },
    "salons": {
        "q": ["nail salon","hair salon","beauty salon","nail shop","barber shop"]
    },
    "restaurants": {
        "q": ["restaurant","pizza place","mexican restaurant","sandwich shop","cafe"]
    },
    "contractors": {
        "q": ["plumber","electrician","hvac","roofer","general contractor","painter"]
    },
    "auto": {
        "q": ["auto repair","mechanic","tire shop","auto body shop","car wash"]
    },
    "medical": {
        "q": ["dentist","chiropractor","physical therapist","optometrist","veterinarian"]
    },
    "retail": {
        "q": ["clothing store","gift shop","antique store","furniture store","bookstore"]
    },
    "fitness": {
        "q": ["gym","fitness center","yoga studio","personal trainer","dance studio"]
    },
}

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
]

P_RE = re.compile(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
BAD_PRE = {"000","111","222","333","444","555","666","777","888","999","123"}
BAD_NAMES = re.compile(
    r'(sign ?in|log ?in|register|subscribe|shopping cart|checkout|'
    r'recovery|cookie|privacy|terms of service|sitemap|page not found|'
    r'just a moment|enable javascript|google|facebook|twitter|instagram|'
    r'youtube|linkedin|cloudflare|captcha|robot|access denied|'
    r'attention required|were sorry|unusual traffic)', re.IGNORECASE)

# Common directory/site words to strip from names
DIR_WORDS = re.compile(
    r'\b(yelp|yellowpages|whitepages|manta|bbb\.org|superpages|'
    r'merchantcircle|angieslist|thumbtack|facebook|nextdoor|'
    r'mapquest|foursquare|citysearch|kudzu|dexknows|hotfrog|'
    r'the real yellow pages|tripadvisor|zomato|grubhub|'
    r'reviews|ratings|phone|phone number|contact|'
    r'best \d+|top \d+|top rated|best rated)\b', re.IGNORECASE)


def good_phone(raw):
    d = re.sub(r'\D', '', raw)
    if len(d) == 11 and d[0] == '1': d = d[1:]
    if len(d) != 10: return False
    if d[:3] in BAD_PRE: return False
    if len(set(d)) < 4: return False
    return True


def clean_phone(raw):
    d = re.sub(r'\D', '', raw)
    if len(d) == 10: return f"({d[:3]}) {d[3:6]}-{d[6:]}"
    if len(d) == 11 and d[0] == '1': return f"({d[1:4]}) {d[4:7]}-{d[7:]}"
    return raw.strip()


def clean_name(raw):
    n = re.sub(r'<[^>]+>', '', raw)
    n = re.sub(r'\s+', ' ', n).strip()
    # Remove common suffixes
    n = re.sub(r'\s*\|\s*.*$', '', n)
    n = re.sub(r'\s*[-–—]\s*.*$', '', n)
    # Remove directory words
    n = DIR_WORDS.sub('', n).strip()
    n = re.sub(r'\s+', ' ', n).strip()
    if len(n) < 3 or BAD_NAMES.search(n): return None
    return n


class Scraper:
    def __init__(self, use_api=False):
        self.s = requests.Session()
        self.leads = {}
        self.use_api = use_api
        self.api_key = os.environ.get("GOOGLE_API_KEY", "") if use_api else ""
        self.stats = {"sources": {}, "api": False}

    def _get(self, url, timeout=15):
        try:
            r = self.s.get(url, headers={
                "User-Agent": random.choice(UAS),
                "Accept": "text/html,*/*",
                "Accept-Language": "en-US,en;q=0.9",
            }, timeout=timeout)
            r.raise_for_status()
            return r
        except: return None

    def _add(self, name, phone, addr, city, state, cat, src, web="", about=""):
        if not good_phone(phone): return False
        n = clean_name(name)
        if not n: return False
        k = f"{re.sub(r'\D','',phone)}:{n.lower()}"
        if k in self.leads: return False

        self.leads[k] = {
            "business_name": n, "phone": clean_phone(phone),
            "address": addr.strip() if addr else "",
            "city": city.strip() if city else "",
            "state": state.strip() if state else "",
            "category": cat, "has_website": "Yes" if web else "No",
            "website": web or "", "website_quality": "check_needed" if web else "none",
            "source": src, "about": about[:300] if about else "",
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self.stats["sources"][src] = self.stats["sources"].get(src, 0) + 1
        return True

    # ───── GOOGLE PLACES API (best) ──────────────────────────────────────

    def google_api(self, query, location, limit=50):
        if not self.api_key: return 0
        self.stats["api"] = True
        count = 0
        # New Places API (searchText): phone + website in ONE call
        try:
            r = self.s.post(
                "https://places.googleapis.com/v1/places:searchText",
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": ("places.displayName.text,places.formattedAddress,"
                                         "places.nationalPhoneNumber,places.websiteUri,places.id"),
                },
                json={"textQuery": f"{query} {location}", "maxResultCount": 20},
                timeout=25,
            )
            data = r.json()
            if data.get("error"):
                if count == 0:
                    print(f"    [API {data['error'].get('status','ERROR')}: {data['error'].get('message','')[:60]}]")
                return count
            for res in data.get("places", []) or []:
                if count >= limit: break
                name = (res.get("displayName") or {}).get("text", "")
                addr = res.get("formattedAddress", "") or ""
                phone = res.get("nationalPhoneNumber", "") or ""
                website = res.get("websiteUri", "") or ""
                if not name or not phone: continue
                city, state = "", ""
                cm = re.search(r',\s*([A-Za-z\s]+),\s*([A-Z]{2})\s+\d{5}', addr)
                if cm: city, state = cm.group(1).strip(), cm.group(2).strip()
                self._add(name, phone, addr, city, state, query, "google_api", website)
                count += 1
        except Exception as e:
            print(f"    [API error: {e}]")
        return count

    # ───── DUCKDUCKGO ────────────────────────────────────────────────────

    def duckduckgo(self, query, location, limit=15):
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(f'{query} {location} phone')}"
        resp = self._get(url)
        if not resp: return 0

        soup = BeautifulSoup(resp.text, "html.parser")
        count = 0

        # First pass: look for phone numbers in snippets on search page
        for res in soup.select(".result"):
            if count >= limit: break
            a = res.select_one(".result__a")
            if not a: continue
            name = a.get_text(strip=True)
            href = a.get("href","")
            snippet = res.select_one(".result__snippet")
            text = (name + " " + (snippet.get_text() if snippet else ""))

            phones = P_RE.findall(text)
            # If no phone in snippet, fetch the page
            if not phones and href:
                pr = self._get(href)
                if pr:
                    phones = P_RE.findall(pr.text)
                    ps = BeautifulSoup(pr.text, "html.parser")
                    if ps.title:
                        name = ps.title.get_text(strip=True)

            for p in phones:
                if good_phone(p):
                    city = location.split(",")[0].strip() if "," in location else ""
                    state = location.split(",")[1].strip() if "," in location else location
                    am = re.search(r'(\d[^,]*,\s*[A-Za-z\s]+,\s*[A-Z]{2})', text)
                    addr = am.group(1) if am else ""
                    self._add(name, p, addr, city, state, query, "duckduckgo", href)
                    count += 1
                    break

        # Second pass: extract phones directly from page text if we got none
        if count == 0:
            phones = P_RE.findall(resp.text)
            snippets = soup.select(".result__snippet")
            for i, p in enumerate(phones):
                if count >= limit: break
                if good_phone(p):
                    sn = snippets[i].get_text() if i < len(snippets) else ""
                    name = sn.split(".")[0].split(",")[0][:60] if sn else "Unknown"
                    self._add(name, p, "", location.split(",")[0].strip() if "," in location else "",
                             location.split(",")[1].strip() if "," in location else location,
                             query, "duckduckgo")
                    count += 1
        return count

    # ───── BING ──────────────────────────────────────────────────────────

    def bing(self, query, location, limit=15):
        url = f"https://www.bing.com/search?q={quote_plus(f'{query} {location} phone')}"
        resp = self._get(url)
        if not resp: return 0

        soup = BeautifulSoup(resp.text, "html.parser")
        count = 0

        for res in soup.select(".b_algo"):
            if count >= limit: break
            h2 = res.select_one("h2 a")
            if not h2: continue
            name = h2.get_text(strip=True)
            href = h2.get("href","")
            cap = res.select_one(".b_caption p")
            text = name + " " + (cap.get_text() if cap else "")

            phones = P_RE.findall(text)
            if not phones and href:
                pr = self._get(href)
                if pr:
                    phones = P_RE.findall(pr.text)
                    ps = BeautifulSoup(pr.text, "html.parser")
                    if ps.title: name = ps.title.get_text(strip=True)

            for p in phones:
                if good_phone(p):
                    city = location.split(",")[0].strip() if "," in location else ""
                    state = location.split(",")[1].strip() if "," in location else location
                    self._add(name, p, "", city, state, query, "bing", href)
                    count += 1
                    break

        if count == 0:
            phones = P_RE.findall(resp.text)
            titles = re.findall(r'<h2><a[^>]*>(.*?)</a></h2>', resp.text, re.DOTALL)
            for i, p in enumerate(phones):
                if count >= limit: break
                if good_phone(p):
                    n = re.sub(r'<[^>]+>','',titles[i]).strip() if i < len(titles) else "Unknown"
                    self._add(n, p, "", location.split(",")[0].strip() if "," in location else "",
                             location.split(",")[1].strip() if "," in location else location,
                             query, "bing")
                    count += 1
        return count

    # ───── COMBINED ──────────────────────────────────────────────────────

    def run(self, queries, location, limit=10):
        total = 0
        for i, q in enumerate(queries):
            print(f"  [{i+1}/{len(queries)}] {q}")

            n = self.google_api(q, location, limit*2)
            if n: print(f"    Google API: {n}"); total += n; time.sleep(0.5)

            if getattr(self, 'use_api', False) and self.api_key:
                print("    (API mode - scrapers skipped)")
                continue

            n = self.duckduckgo(q, location, limit)
            print(f"    DuckDuckGo: {n}"); total += n; time.sleep(random.uniform(0.3,1))

            n = self.bing(q, location, limit)
            print(f"    Bing: {n}"); total += n; time.sleep(random.uniform(0.3,1))

        return total

    def export(self, base):
        if not self.leads:
            print("  No leads.")
            return
        fields = ["business_name","phone","address","city","state",
                   "category","has_website","website","website_quality",
                   "source","about","scraped_at"]
        for ext in ["csv","json"]:
            fn = f"{base}.{ext}"
            with open(fn, "w", newline="" if ext=="csv" else None, encoding="utf-8") as f:
                if ext == "csv":
                    w = csv.DictWriter(f, fieldnames=fields)
                    w.writeheader(); w.writerows(self.leads.values())
                else:
                    json.dump(list(self.leads.values()), f, indent=2, ensure_ascii=False)
            print(f"  => {fn} ({len(self.leads)} leads)")

    def summary(self):
        L = list(self.leads.values())
        print(f"\n{'='*60}")
        print(f"  RESULTS: {len(L)} unique leads")
        print(f"  Sources: {', '.join(f'{k}={v}' for k,v in sorted(self.stats['sources'].items()))}")
        if self.stats["api"]: print(f"  Google API: YES")

        states, cats, ws, wo = {}, {}, 0, 0
        for l in L:
            s = l.get("state",""); c = l.get("category","")
            if s: states[s] = states.get(s,0)+1
            if c: cats[c] = cats.get(c,0)+1
            if l.get("has_website")=="Yes": ws += 1
            else: wo += 1

        if cats:
            print(f"\n  By category:")
            for c,n in sorted(cats.items(),key=lambda x:-x[1])[:10]:
                print(f"    {c}: {n}")
        if states:
            print(f"\n  Top states:")
            for s,n in sorted(states.items(),key=lambda x:-x[1])[:10]:
                print(f"    {s}: {n}")
        print(f"\n  With website: {ws}  Without: {wo}")
        print(f"{'='*60}")
        if wo > 0:
            print(f"\n  {wo} leads WITHOUT a website — prime targets!")
        print(f"  All leads saved in current folder.")
        print(f"  {L[0]['scraped_at']}")


def main():
    p = argparse.ArgumentParser(
        description="ML&R Lead Scraper v4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""Presets: {', '.join(PRESETS.keys())}

Examples:
  python lead_scraper.py -p lawyers -l "Dallas, TX" -L 30
  python lead_scraper.py -p salons -l "Phoenix, AZ" --api
  python lead_scraper.py -c "nail salon" -l "Minneapolis, MN"
  python lead_scraper.py -p lawyers -l "Chicago, IL" -o chicago_lawyers

  # Multi-city batch:
  python lead_scraper.py -p lawyers --cities "Dallas,TX|Houston,TX|Austin,TX" --api

  # From file (one city per line, format: City, ST):
  python lead_scraper.py -p salons --cityfile cities.txt --api

For Google Places API (free): set $env:GOOGLE_API_KEY = "your_key"
""")
    p.add_argument("-c","--category", help="Business type")
    p.add_argument("-p","--preset", choices=list(PRESETS.keys()), help="Preset")
    p.add_argument("-l","--location", help='City, State (single city)')
    p.add_argument("--cities", help="Pipe-separated: Dallas,TX|Houston,TX|Austin,TX")
    p.add_argument("--cityfile", help="File with one City, State per line")
    p.add_argument("-L","--limit", type=int, default=20, help="Leads per source per query")
    p.add_argument("-o","--output", help="Output filename (batch adds _combined)")
    p.add_argument("--api", action="store_true", help="Use Google Places API")

    args = p.parse_args()
    if not args.category and not args.preset: p.error("Need --category or --preset")
    if args.category and args.preset: p.error("Use --category OR --preset")

    # Collect cities
    cities = []
    if args.cities:
        cities = [c.strip() for c in args.cities.split("|") if c.strip()]
    elif args.cityfile:
        with open(args.cityfile, "r", encoding="utf-8") as f:
            cities = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    elif args.location:
        cities = [args.location]
    else:
        p.error("Need --location, --cities, or --cityfile")

    s = Scraper(use_api=args.api)
    queries = PRESETS[args.preset]["q"] if args.preset else [args.category]
    label = args.preset or args.category.replace(" ","_")

    print(f"\n  Target: {args.preset or args.category}")
    print(f"  Cities: {len(cities)} ({', '.join(cities[:5])}{'...' if len(cities)>5 else ''})")
    print(f"  Queries: {len(queries)}, Limit: {args.limit}")
    if args.api:
        print(f"  Google API: {'ENABLED' if s.api_key else 'NO KEY (set GOOGLE_API_KEY)'}")
    print(f"{'-'*60}")

    total_leads = 0
    for ci, city in enumerate(cities):
        print(f"\n{'='*60}")
        print(f"  CITY [{ci+1}/{len(cities)}]: {city}")
        print(f"{'='*60}")
        s.run(queries, city, args.limit)
        total_leads += len(s.leads) - total_leads  # this is wrong, just for display

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = args.output or f"leads_{label}_{ts}"
    print(f"\n{'-'*60}")
    print("  Exporting...")
    s.export(base)
    s.summary()


if __name__ == "__main__":
    main()
