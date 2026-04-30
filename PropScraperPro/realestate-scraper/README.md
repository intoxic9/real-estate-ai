# PropScraper Pro

A professional, free, and legally compliant real estate data scraper with:
- Craigslist public RSS scraping
- Groq AI (Llama 3) contact extraction
- Google Sheets auto-sync
- Admin panel with API key management
- Full listings browser with search & filter
- CSV export

---

## Quick Start

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
python app.py
```

Open http://localhost:5000 in your browser.

---

## Admin Setup

Go to http://localhost:5000/admin

**Default credentials:** `admin` / `admin123`
(Change this immediately after first login)

---

## Groq API Key Setup

1. Go to https://console.groq.com
2. Sign up (free)
3. Click API Keys → Create New Key
4. Copy the key (starts with `gsk_`)
5. Paste into Admin → Groq API Key field → Save

Groq AI is used to extract phone, email, beds, baths, price from unstructured listing text using Llama 3.

---

## Google Sheets Setup

### Step 1 — Create a Google Cloud project
1. Go to https://console.cloud.google.com
2. Create a new project
3. Go to APIs & Services → Enable APIs → Enable "Google Sheets API"

### Step 2 — Create a Service Account
1. Go to IAM & Admin → Service Accounts
2. Click "Create Service Account"
3. Give it a name, click Create
4. Skip optional steps, click Done
5. Click the service account → Keys tab → Add Key → JSON
6. Download the JSON file

### Step 3 — Share your Google Sheet
1. Create a new Google Sheet at https://sheets.google.com
2. Click Share
3. Paste the service account email from the JSON (looks like `name@project.iam.gserviceaccount.com`)
4. Give it **Editor** access

### Step 4 — Configure in Admin panel
1. Go to http://localhost:5000/admin
2. Paste the Sheet ID (from the URL: `docs.google.com/spreadsheets/d/[SHEET_ID]/edit`)
3. Paste the full JSON content into "Service Account JSON"
4. Click Save Sheet Config

### Step 5 — Sync data
After scraping listings, click "Sync Unsynced Listings → Sheet" in the Admin panel.

---

## Scraping

1. Go to http://localhost:5000/scraper
2. Select a city (or type a custom Craigslist subdomain)
3. Choose For Rent or For Sale
4. Click "Launch Scrape Job"
5. Watch the progress bar in real-time

Scraper limits:
- Max 50 listings per job
- 1 second delay between requests (rate limited)
- Only public RSS data from Craigslist
- Respects robots.txt

---

## Legal Notes

- Only publicly visible listing data is collected
- No login bypass or authentication is used
- Data is rate-limited to avoid server overload
- Contact info is only extracted from publicly posted text
- For personal/research use — do not resell contact data
- Compliant with Craigslist public RSS feeds

---

## File Structure

```
realestate-scraper/
├── app.py                  # Main Flask app
├── requirements.txt        # Python dependencies
├── data/
│   ├── realestate.db      # SQLite database (auto-created)
│   └── config.json        # API keys (auto-created)
├── static/
│   ├── css/style.css      # Stylesheet
│   └── js/main.js         # JavaScript
└── templates/
    ├── base.html          # Layout
    ├── index.html         # Home page
    ├── dashboard.html     # Dashboard
    ├── scraper.html       # Scraper
    ├── listings.html      # Listings browser
    └── admin.html         # Admin panel
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/start_scrape` | POST | Launch a scrape job |
| `/api/job_status/<id>` | GET | Poll job progress |
| `/api/listings` | GET | Get all listings as JSON |
| `/api/stats` | GET | Get summary stats |
| `/api/export_csv` | GET | Download all listings as CSV |
| `/api/delete_listing/<id>` | DELETE | Delete a listing (admin) |
