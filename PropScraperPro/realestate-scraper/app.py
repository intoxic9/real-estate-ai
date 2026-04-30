from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json, os, time, re, threading, sqlite3, hashlib
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import feedparser
import gspread
from google.oauth2.service_account import Credentials
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

app.secret_key = os.urandom(24)

DB_PATH = "data/realestate.db"
CONFIG_PATH = "data/config.json"

# ── DB INIT ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT, price TEXT, address TEXT, city TEXT,
            beds TEXT, baths TEXT, sqft TEXT,
            phone TEXT, email TEXT, contact_name TEXT,
            description TEXT, url TEXT UNIQUE,
            source TEXT, listing_type TEXT,
            lat TEXT, lng TEXT,
            posted_at TEXT,
            synced_to_sheet INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS scrape_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT, listing_type TEXT, status TEXT DEFAULT 'pending',
            total INTEGER DEFAULT 0, processed INTEGER DEFAULT 0,
            started_at TEXT, finished_at TEXT,
            error TEXT
        );
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        );
    """)
    # Default admin: admin / admin123
    pw = hashlib.sha256("admin123".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO admin_users (username, password_hash) VALUES (?,?)", ("admin", pw))
    conn.commit()
    conn.close()

# ── CONFIG ───────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"groq_api_key": "", "google_sheet_id": "", "google_creds": {}}

def save_config(cfg):
    os.makedirs("data", exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)

# ── GROQ AI ──────────────────────────────────────────────
def groq_extract(text, api_key):
    """Use Groq to extract structured contact info from listing text."""
    if not api_key or len(text) < 20:
        return {}
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "llama3-8b-8192",
                "messages": [{
                    "role": "user",
                    "content": f""" Extract contact info and property details. 
Return ONLY valid JSON.
IMPORTANT: Do NOT mix the price with the street address. If a number like '285' appears after a price like '$1,650', '285' is likely the house number, NOT part of the price.
Keys: phone, email, contact_name, beds, baths, sqft, price, address. Use null for missing.

Listing text:
{text[:2000]}

JSON:"""
                }],
                "max_tokens": 300,
                "temperature": 0.1
            },
            timeout=15
        )
        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip()
        # strip markdown fences
        raw = re.sub(r"```json|```", "", raw).strip()
        return json.loads(raw)
    except Exception as e:
        return {}

# ── SCRAPER CORE ─────────────────────────────────────────
def extract_contact_regex(text):
    # Aggressive phone regex for US/International formats
    phone_pattern = r'(?:(?:\+?1\s*(?:[.-]\s*)?)?(?:\(\s*([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9])\s*\)|([2-9]1[02-9]|[2-9][02-8]1|[2-9][02-8][02-9]))\s*(?:[.-]\s*)?)?([2-9]1[02-9]|[2-9][02-9]1|[2-9][02-9]{2})\s*(?:[.-]\s*)?([0-9]{4})(?:\s*(?:#|x\.?|ext\.?|extension)\s*(\d+))?'
    phones = re.findall(r'(\d{3}[-\.\s]??\d{3}[-\.\s]??\d{4}|\(\d{3}\)\s*\d{3}[-\.\s]??\d{4}|\d{10})', text)
    emails = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', text)
    return list(set(phones))[:2], list(set(emails))[:2]

def scrape_craigslist(city, listing_type, job_id, api_key, query="", min_price="", max_price="", min_beds=""):
    """Scrape Craigslist listings with advanced filters."""
    cat = "reo" if listing_type == "sale" else "apa"
    
    # Construct filter-aware URL
    params = []
    if query: params.append(f"query={query}")
    if min_price: params.append(f"min_price={min_price}")
    if max_price: params.append(f"max_price={max_price}")
    if min_beds: params.append(f"min_bedrooms={min_beds}")
    
    query_str = "&" + "&".join(params) if params else ""
    url = f"https://{city}.craigslist.org/search/{cat}?{query_str}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("UPDATE scrape_jobs SET status='running', started_at=? WHERE id=?",
                  (datetime.now().isoformat(), job_id))
        conn.commit()
        
        logger.info(f"Starting scrape for {city} at {url}")
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Broader set of selectors for listing containers
        items = soup.select(".cl-static-search-result") or \
                soup.select(".result-row") or \
                soup.select("li[title]") or \
                soup.find_all("li", class_=re.compile(r"result|item"))
                
        items = [it for it in items if it.find("a")] # Must have a link
        items = items[:50] 
        
        logger.info(f"Found {len(items)} items to process")
        c.execute("UPDATE scrape_jobs SET total=? WHERE id=?", (len(items), job_id))
        conn.commit()
        
        if not items:
            logger.warning("No items found on page. Craigslist might be blocking or layout changed.")
        
        for i, item in enumerate(items):
            try:
                # 1. Extract basic info and real date
                title_tag = item.select_one(".titlestring") or item.select_one(".result-title") or item.find("a", href=re.compile(r"/[a-z]{3}/d/"))
                date_tag = item.select_one("time") or item.select_one(".result-date")
                posted_val = date_tag.get_text(strip=True) if date_tag else datetime.now().strftime('%Y-%m-%d')
                
                if not title_tag: continue
                
                title = title_tag.get_text(strip=True)
                link = title_tag.get("href")
                if link and not link.startswith("http"):
                    link = f"https://{city}.craigslist.org{link}"
                
                # 2. DEEP SCRAPE: Visit the individual listing page
                logger.info(f"Deep scraping: {link}")
                detail_resp = requests.get(link, headers=headers, timeout=10)
                detail_soup = BeautifulSoup(detail_resp.text, "html.parser")
                
                # Extract full description
                desc_tag = detail_soup.select_one("#postingbody")
                full_desc = desc_tag.get_text(strip=True).replace("QR Code Link to This Post", "") if desc_tag else title
                
                # Extract actual price from detail page
                price_tag = detail_soup.select_one(".price") or detail_soup.select_one(".result-price")
                price = price_tag.get_text(strip=True) if price_tag else "Contact for price"
                
                # Extract address/location
                addr_tag = detail_soup.select_one(".mapaddress") or detail_soup.select_one("div.viewing-map-link")
                address = addr_tag.get_text(strip=True) if addr_tag else ""

                # 3. Use AI to parse the rich text for specs
                ai = {}
                if api_key:
                    # Send title + first 1000 chars of description to AI
                    ai = groq_extract(f"{title}\n{full_desc[:1000]}", api_key)
                
                phones, emails = extract_contact_regex(full_desc)
                
                row = {
                    "title": title,
                    "price": ai.get("price") or price,
                    "address": ai.get("address") or address,
                    "city": city,
                    "beds": ai.get("beds") or "",
                    "baths": ai.get("baths") or "",
                    "sqft": ai.get("sqft") or "",
                    "phone": ai.get("phone") or (phones[0] if phones else ""),
                    "email": ai.get("email") or (emails[0] if emails else ""),
                    "contact_name": ai.get("contact_name") or "",
                    "description": full_desc[:1000],
                    "url": link,
                    "source": "craigslist",
                    "listing_type": listing_type,
                    "posted_at": posted_val
                }
                c.execute("""INSERT OR IGNORE INTO listings
                    (title,price,address,city,beds,baths,sqft,phone,email,contact_name,description,url,source,listing_type,posted_at)
                    VALUES (:title,:price,:address,:city,:beds,:baths,:sqft,:phone,:email,:contact_name,:description,:url,:source,:listing_type,:posted_at)
                """, row)
                conn.commit()
                c.execute("UPDATE scrape_jobs SET processed=? WHERE id=?", (i+1, job_id))
                conn.commit()
                
                # Throttling to prevent IP bans
                time.sleep(1.2)
            except Exception as e:
                logger.error(f"Error processing item {i}: {e}")
                continue
                
        c.execute("UPDATE scrape_jobs SET status='done', finished_at=? WHERE id=?",
                  (datetime.now().isoformat(), job_id))
        conn.commit()
        logger.info(f"Scrape job {job_id} completed.")
    except Exception as e:
        logger.error(f"Scrape job {job_id} failed: {e}")
        c.execute("UPDATE scrape_jobs SET status='error', error=?, finished_at=? WHERE id=?",
                  (str(e), datetime.now().isoformat(), job_id))
        conn.commit()
    finally:
        conn.close()



# ── GOOGLE SHEETS SYNC ────────────────────────────────────
def sync_to_sheet(sheet_id, creds_json):
    if not sheet_id or not creds_json:
        return 0, "Missing sheet ID or credentials"
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(creds_json, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(sheet_id)
        ws = sh.sheet1
        headers = ["ID","Title","Price","Address","City","Beds","Baths","Sqft",
                   "Phone","Email","Contact Name","Description","URL","Source","Type","Created At"]
        if ws.row_count == 0 or ws.cell(1,1).value != "ID":
            ws.insert_row(headers, 1)
        conn = get_db(); c = conn.cursor()
        rows = c.execute("SELECT * FROM listings WHERE synced_to_sheet=0").fetchall()
        batch = []
        for r in rows:
            batch.append([r["id"],r["title"],r["price"],r["address"],r["city"],
                          r["beds"],r["baths"],r["sqft"],r["phone"],r["email"],
                          r["contact_name"],r["description"][:200],r["url"],
                          r["source"],r["listing_type"],r["created_at"]])
        if batch:
            ws.append_rows(batch)
            ids = [r["id"] for r in rows]
            c.executemany("UPDATE listings SET synced_to_sheet=1 WHERE id=?", [(i,) for i in ids])
            conn.commit()
        conn.close()
        return len(batch), None
    except Exception as e:
        return 0, str(e)

# ── AUTH ─────────────────────────────────────────────────
def is_admin():
    return session.get("admin_logged_in")

# ── ROUTES ───────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/dashboard")
def dashboard():
    conn = get_db(); c = conn.cursor()
    stats = {
        "total": c.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
        "with_phone": c.execute("SELECT COUNT(*) FROM listings WHERE phone!=''").fetchone()[0],
        "with_email": c.execute("SELECT COUNT(*) FROM listings WHERE email!=''").fetchone()[0],
        "synced": c.execute("SELECT COUNT(*) FROM listings WHERE synced_to_sheet=1").fetchone()[0],
        "jobs": c.execute("SELECT COUNT(*) FROM scrape_jobs").fetchone()[0],
    }
    recent = c.execute("SELECT * FROM listings ORDER BY created_at DESC LIMIT 10").fetchall()
    jobs   = c.execute("SELECT * FROM scrape_jobs ORDER BY id DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("dashboard.html", stats=stats,
                           recent=[dict(r) for r in recent],
                           jobs=[dict(j) for j in jobs])

@app.route("/api/suggestions")
def suggestions():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    
    conn = get_db_connection()
    cursor = conn.cursor()
    # Search for matching cities or areas
    cursor.execute("""
        SELECT DISTINCT city FROM listings WHERE UPPER(city) LIKE UPPER(?) 
        UNION 
        SELECT DISTINCT area FROM listings WHERE UPPER(area) LIKE UPPER(?)
        LIMIT 10
    """, (f"%{q}%", f"%{q}%"))
    results = [row[0] for row in cursor.fetchall() if row[0]]
    conn.close()
    return jsonify(results)

@app.route("/listings")
def listings():
    """Aggressive search logic with deep logging for diagnostics."""
    try:
        # 1. Capture All Inputs
        q = request.args.get("q", "").strip()
        city = request.args.get("city", "")
        ltype = request.args.get("type", "")
        min_p = request.args.get("min_p", "")
        max_p = request.args.get("max_p", "")
        beds = request.args.get("beds", "")
        src = request.args.get("src", "")
        has_phone = request.args.get("has_phone", "")
        page = int(request.args.get("page", 1))
        per = 20

        # 2. Force Logging to File for Verification
        with open("search_log.txt", "a") as f:
            f.write(f"\n[{datetime.now()}] SEARCH: q='{q}', city='{city}', min='{min_p}', max='{max_p}', has_phone='{has_phone}'\n")

        conn = get_db(); c = conn.cursor()
        where = ["1=1"]
        params = []
        
        # 3. Aggressive Case-Insensitive Search
        if q:
            where.append("(UPPER(title) LIKE UPPER(?) OR UPPER(description) LIKE UPPER(?))")
            params.extend([f"%{q}%", f"%{q}%"])
        
        if city:
            where.append("UPPER(city) LIKE UPPER(?)")
            params.append(f"%{city}%")
            
        if ltype:
            where.append("listing_type = ?")
            params.append(ltype)

        # 4. Bulletproof Case-Insensitive Price Parsing
        # We wrap the price in UPPER() so our REPLACE targets (AED, MONTH, etc) always match.
        clean_price = "REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(price), 'AED', ''), '$', ''), ',', ''), 'MONTH', ''), ' ', '')"
        price_sql = f"CAST({clean_price} AS FLOAT)"
        
        if min_p and min_p.replace('.','',1).isdigit():
            where.append(f"{price_sql} >= ?")
            params.append(float(min_p))
        if max_p and max_p.replace('.','',1).isdigit():
            where.append(f"{price_sql} <= ?")
            params.append(float(max_p))

        # 5. Smart Beds Logic (Studio = 0, Case-Insensitive)
        if beds and beds.isdigit():
            beds_sql = "CAST(REPLACE(UPPER(beds), 'STUDIO', '0') AS INTEGER)"
            where.append(f"{beds_sql} >= ?")
            params.append(int(beds))
            
        if src:
            where.append("source = ?")
            params.append(src)
            
        if has_phone:
            where.append("(phone IS NOT NULL AND phone != '' AND phone != 'None' AND phone != 'N/A')")

        where_str = " AND ".join(where)
        
        # 5. Execute with Verification
        total = c.execute(f"SELECT COUNT(*) FROM listings WHERE {where_str}", params).fetchone()[0]
        rows = c.execute(f"SELECT * FROM listings WHERE {where_str} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                        params + [per, (page-1)*per]).fetchall()
        
        cities = [r[0] for r in c.execute("SELECT DISTINCT city FROM listings WHERE city != '' ORDER BY city").fetchall()]
        conn.close()

        return render_template("listings.html", 
                               listings=[dict(r) for r in rows],
                               total=total, page=page, per=per,
                               pages=(total+per-1)//per, 
                               q=q, city=city, ltype=ltype, 
                               min_p=min_p, max_p=max_p, beds=beds, src=src, has_phone=has_phone,
                               cities=cities,
                               now_date=datetime.now().strftime('%Y-%m-%d'),
                               debug_query=f"WHERE {where_str} | Params: {params}")
    except Exception as e:
        with open("search_log.txt", "a") as f: f.write(f"ERROR: {str(e)}\n")
        return f"Search System Error: {str(e)}", 500

@app.route("/scraper")
def scraper():
    conn = get_db(); c = conn.cursor()
    jobs = c.execute("SELECT * FROM scrape_jobs ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return render_template("scraper.html", jobs=[dict(j) for j in jobs])

@app.route("/admin", methods=["GET","POST"])
def admin():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "login":
            u = request.form.get("username")
            p = hashlib.sha256(request.form.get("password","").encode()).hexdigest()
            conn = get_db(); c = conn.cursor()
            user = c.execute("SELECT * FROM admin_users WHERE username=? AND password_hash=?", (u,p)).fetchone()
            conn.close()
            if user:
                session["admin_logged_in"] = True
                session["admin_user"] = u
            else:
                return render_template("admin.html", error="Invalid credentials", cfg=load_config())
        elif action == "logout":
            session.clear()
        elif action == "save_config" and is_admin():
            cfg = load_config()
            if "groq_api_key" in request.form:
                cfg["groq_api_key"] = request.form.get("groq_api_key", "")
            if "google_sheet_id" in request.form:
                cfg["google_sheet_id"] = request.form.get("google_sheet_id", "")
            if "google_creds" in request.form:
                raw = request.form.get("google_creds", "").strip()
                try: cfg["google_creds"] = json.loads(raw) if raw else {}
                except: pass
            save_config(cfg)

        elif action == "sync_sheet" and is_admin():
            cfg = load_config()
            n, err = sync_to_sheet(cfg["google_sheet_id"], cfg["google_creds"])
            return render_template("admin.html", cfg=cfg, sync_result=f"Synced {n} rows" if not err else f"Error: {err}")
        elif action == "change_password" and is_admin():
            np = hashlib.sha256(request.form.get("new_password","").encode()).hexdigest()
            conn = get_db(); c = conn.cursor()
            c.execute("UPDATE admin_users SET password_hash=? WHERE username=?", (np, session["admin_user"]))
            conn.commit(); conn.close()
    return render_template("admin.html", cfg=load_config())

def scrape_dubai(listing_type, job_id, api_key):
    """Scrape Dubai listings with anti-blocking and retry logic."""
    cat = "property-for-sale" if listing_type == "sale" else "property-for-rent"
    url = f"https://dubai.dubizzle.com/en/{cat}/residential/"
    
    # Advanced Anti-Blocking Headers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }
    
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("UPDATE scrape_jobs SET status='running', started_at=? WHERE id=?",
                  (datetime.now().isoformat(), job_id))
        conn.commit()
        
        logger.info(f"Starting Dubai scrape at {url}")
        
        # Retry Logic (3 Attempts)
        resp = None
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=25)
                resp.raise_for_status()
                break
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {e}")
                time.sleep(2 * (attempt + 1))
        
        if not resp or resp.status_code != 200:
            raise Exception(f"Failed to reach Dubizzle after 3 attempts. Status: {resp.status_code if resp else 'No Resp'}")

        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Dubizzle listing cards (Multi-selector for layout changes)
        items = soup.select('[data-testid="listing-card"]') or \
                soup.select(".listing-card") or \
                soup.find_all("div", class_=re.compile(r"ListItem"))
                
        items = items[:30] 
        c.execute("UPDATE scrape_jobs SET total=? WHERE id=?", (len(items), job_id))
        conn.commit()
        
        for i, item in enumerate(items):
            try:
                title_tag = item.select_one('[data-testid="listing-title"]') or item.find("h2")
                price_tag = item.select_one('[data-testid="listing-price"]') or item.select_one(".price")
                link_tag  = item.find("a", href=True)
                
                title = title_tag.get_text(strip=True) if title_tag else "Dubai Property"
                price = price_tag.get_text(strip=True) if price_tag else "Price on Call"
                link = link_tag["href"] if link_tag else url
                if link.startswith("/"): link = f"https://dubai.dubizzle.com{link}"

                # AUTO DEEP SCRAPE: Visit the property page immediately
                logger.info(f"Auto-Deep Scraping Dubai: {link}")
                try:
                    d_resp = requests.get(link, headers=headers, timeout=15)
                    d_soup = BeautifulSoup(d_resp.text, "html.parser")
                    
                    # Look for address in deep page
                    addr_tag = d_soup.select_one('[data-testid="listing-location"]') or d_soup.select_one(".location")
                    address = addr_tag.get_text(strip=True) if addr_tag else "Dubai, UAE"
                    
                    # Look for phone/email patterns in description
                    body = d_soup.get_text()
                    phones, emails = extract_contact_regex(body)
                except:
                    address = "Dubai, UAE"
                    phones, emails = [], []
                
                # Use AI to extract better details from title/snippet if possible
                ai = {}
                if api_key:
                    ai = groq_extract(title, api_key)
                
                row = {
                    "title": title,
                    "price": ai.get("price") or price,
                    "address": address if address != "Dubai, UAE" else (ai.get("address") or address),
                    "city": "Dubai",
                    "beds": ai.get("beds") or "",
                    "baths": ai.get("baths") or "",
                    "sqft": ai.get("sqft") or "",
                    "phone": ai.get("phone") or (phones[0] if phones else ""),
                    "email": ai.get("email") or (emails[0] if emails else ""),
                    "contact_name": ai.get("contact_name") or "",
                    "description": title,
                    "url": link,
                    "source": "dubizzle",
                    "listing_type": listing_type,
                    "posted_at": datetime.now().strftime('%Y-%m-%d')
                }
                c.execute("""INSERT OR IGNORE INTO listings
                    (title,price,address,city,beds,baths,sqft,phone,email,contact_name,description,url,source,listing_type,posted_at)
                    VALUES (:title,:price,:address,:city,:beds,:baths,:sqft,:phone,:email,:contact_name,:description,:url,:source,:listing_type,:posted_at)
                """, row)
                conn.commit()
                c.execute("UPDATE scrape_jobs SET processed=? WHERE id=?", (i+1, job_id))
                conn.commit()
                time.sleep(0.5)
            except Exception as e:
                logger.error(f"Error processing item {i}: {e}")
                continue
                
        c.execute("UPDATE scrape_jobs SET status='done', finished_at=? WHERE id=?",
                  (datetime.now().isoformat(), job_id))
        conn.commit()
    except Exception as e:
        logger.error(f"Dubai scrape failed: {e}")
        c.execute("UPDATE scrape_jobs SET status='error', error=?, finished_at=? WHERE id=?",
                  (str(e), datetime.now().isoformat(), job_id))
        conn.commit()
    finally:
        conn.close()

def scrape_sulekha(city, listing_type, job_id, api_key, query=""):
    """Scrape Sulekha USA listings."""
    # Sulekha uses a different URL structure, often category-based
    search = query.replace(" ", "+") if query else "rentals"
    url = f"https://us.sulekha.com/{search}-in-{city}"
    headers = {"User-Agent": "Mozilla/5.0"}
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("UPDATE scrape_jobs SET status='running', started_at=? WHERE id=?", (datetime.now().isoformat(), job_id))
        conn.commit()
        resp = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        items = soup.select(".list-item") or soup.select(".card")
        c.execute("UPDATE scrape_jobs SET total=? WHERE id=?", (len(items), job_id))
        conn.commit()
        for i, item in enumerate(items[:20]):
            title = item.find("h3").get_text(strip=True) if item.find("h3") else "Sulekha Listing"
            price = item.select_one(".price").get_text(strip=True) if item.select_one(".price") else ""
            link = item.find("a")["href"] if item.find("a") else url
            if not link.startswith("http"): link = f"https://us.sulekha.com{link}"
            c.execute("INSERT OR IGNORE INTO listings (title,price,city,url,source,listing_type) VALUES (?,?,?,?,?,?)",
                      (title, price, city, link, "sulekha", listing_type))
            conn.commit()
            c.execute("UPDATE scrape_jobs SET processed=? WHERE id=?", (i+1, job_id))
            conn.commit()
        c.execute("UPDATE scrape_jobs SET status='done', finished_at=? WHERE id=?", (datetime.now().isoformat(), job_id))
        conn.commit()
    except Exception as e:
        c.execute("UPDATE scrape_jobs SET status='error', error=? WHERE id=?", (str(e), job_id))
        conn.commit()
    finally: conn.close()

def scrape_zillow(city, listing_type, job_id, api_key, query=""):
    """Zillow Scraper (Simulation/Basic)."""
    # Zillow is extremely hard to scrape via requests; this is a placeholder/basic attempt
    url = f"https://www.zillow.com/{city}/"
    conn = get_db(); c = conn.cursor()
    try:
        c.execute("UPDATE scrape_jobs SET status='running', started_at=? WHERE id=?", (datetime.now().isoformat(), job_id))
        conn.commit()
        # Zillow often returns 403 to requests.get; we'll simulate a few results for now or try one fetch
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if resp.status_code == 403:
            raise Exception("Zillow blocked the request (403 Forbidden). Requires Proxy/Browser.")
        # ... logic for parsing Zillow JSON if success ...
        c.execute("UPDATE scrape_jobs SET status='done' WHERE id=?", (job_id,))
        conn.commit()
    except Exception as e:
        c.execute("UPDATE scrape_jobs SET status='error', error=? WHERE id=?", (str(e), job_id))
        conn.commit()
    finally: conn.close()

# ── API ENDPOINTS ─────────────────────────────────────────
@app.route("/api/start_scrape", methods=["POST"])
def api_start_scrape():
    data = request.json or {}
    city_input  = data.get("city","newyork").strip().lower().replace(" ","")
    source_input= data.get("source", "craigslist")
    query = data.get("query", "")
    ltype = data.get("listing_type","rent")
    min_p = data.get("min_price", "")
    max_p = data.get("max_price", "")
    beds  = data.get("min_beds", "")
    
    cfg = load_config()
    api_key = cfg.get("groq_api_key","")

    # Define targets
    if city_input == "all_usa":
        cities = ["newyork", "losangeles", "chicago", "miami"]
    elif city_input == "dubai":
        cities = ["dubai"]
        sources = ["dubai"]
    else:
        cities = [city_input]

    sources = ["craigslist", "sulekha"] if source_input == "all" else [source_input]
    if "dubai" in cities:
        sources = ["dubai"]

    job_ids = []
    for src in sources:
        for cty in cities:
            conn = get_db(); cur = conn.cursor()
            cur.execute("INSERT INTO scrape_jobs (city, listing_type, status) VALUES (?,?,?)", (f"{cty} ({src})", ltype, "pending"))
            job_id = cur.lastrowid
            conn.commit(); conn.close()
            job_ids.append(job_id)

            if src == "dubai":
                target, args = scrape_dubai, (ltype, job_id, api_key)
            elif src == "sulekha":
                target, args = scrape_sulekha, (cty, ltype, job_id, api_key, query)
            elif src == "zillow":
                target, args = scrape_zillow, (cty, ltype, job_id, api_key, query)
            else: # Craigslist
                target, args = scrape_craigslist, (cty, ltype, job_id, api_key, query, min_p, max_p, beds)
            
            t = threading.Thread(target=target, args=args, daemon=True)
            t.start()
            time.sleep(1) # Small stagger to prevent CPU spike
    
    return jsonify({"ok": True, "job_id": job_ids[0] if job_ids else 0, "all_jobs": job_ids})

@app.route("/api/fetch_details/<int:id>", methods=["POST"])
def api_fetch_details(id):
    """Deep scrape a single listing on demand with bulletproof JSON response."""
    try:
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT * FROM listings WHERE id=?", (id,))
        l = c.fetchone()
        if not l: 
            conn.close()
            return jsonify({"ok":False, "error":"Listing ID not found in database."})
        l = dict(l)
        conn.close()

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        # Visit URL
        resp = requests.get(l["url"], headers=headers, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 1. Full Description
        desc_tag = soup.select_one("#postingbody") or soup.select_one(".description") or soup.select_one("section#postingbody")
        desc = desc_tag.get_text(strip=True).replace("QR Code Link to This Post", "") if desc_tag else l["description"]
        
        # 2. Extract Phone/Email
        phones, emails = extract_contact_regex(desc)
        
        # 3. Address
        addr_tag = soup.select_one(".mapaddress") or soup.select_one("div.viewing-map-link") or soup.select_one(".postingtitletext small")
        addr = addr_tag.get_text(strip=True).strip("()") if addr_tag else l["address"]
        
        # 4. Update DB
        conn = get_db(); c = conn.cursor()
        c.execute("""UPDATE listings SET 
                     phone=?, email=?, address=?, description=?
                     WHERE id=?""",
                  (phones[0] if phones else l["phone"], 
                   emails[0] if emails else l["email"], 
                   addr or l["address"], desc[:1000], id))
        conn.commit(); conn.close()
        
        return jsonify({"ok":True, "found": bool(phones or emails)})
    except Exception as e:
        logger.error(f"Manual fetch failed for ID {id}: {e}")
        return jsonify({"ok":False, "error": f"Server Error: {str(e)}"})
def api_job_status(job_id):
    conn = get_db(); c = conn.cursor()
    job = c.execute("SELECT * FROM scrape_jobs WHERE id=?", (job_id,)).fetchone()
    conn.close()
    if not job: return jsonify({"error": "not found"}), 404
    return jsonify(dict(job))

@app.route("/api/listings")
def api_listings():
    conn = get_db(); c = conn.cursor()
    rows = c.execute("SELECT * FROM listings ORDER BY created_at DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/stats")
def api_stats():
    conn = get_db(); c = conn.cursor()
    return jsonify({
        "total": c.execute("SELECT COUNT(*) FROM listings").fetchone()[0],
        "with_phone": c.execute("SELECT COUNT(*) FROM listings WHERE phone!=''").fetchone()[0],
        "with_email": c.execute("SELECT COUNT(*) FROM listings WHERE email!=''").fetchone()[0],
        "synced": c.execute("SELECT COUNT(*) FROM listings WHERE synced_to_sheet=1").fetchone()[0],
    })

@app.route("/api/delete_listing/<int:lid>", methods=["DELETE"])
def api_delete(lid):
    if not is_admin(): return jsonify({"error":"unauthorized"}),401
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM listings WHERE id=?", (lid,))
    conn.commit(); conn.close()
    return jsonify({"ok":True})

@app.route("/api/export_csv")
def api_export_csv():
    import csv, io
    conn = get_db(); c = conn.cursor()
    rows = c.execute("SELECT * FROM listings ORDER BY created_at DESC").fetchall()
    conn.close()
    output = io.StringIO()
    w = csv.writer(output)
    w.writerow(["ID","Title","Price","Address","City","Beds","Baths","Sqft","Phone","Email","Contact","Description","URL","Source","Type","Created"])
    for r in rows:
        w.writerow([r["id"],r["title"],r["price"],r["address"],r["city"],r["beds"],r["baths"],
                    r["sqft"],r["phone"],r["email"],r["contact_name"],r["description"],r["url"],r["source"],r["listing_type"],r["created_at"]])
    from flask import Response
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition":"attachment;filename=listings.csv"})

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
