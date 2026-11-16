# Places Lead Scraper

An automated lead-generation pipeline built on the **Google Places API (New)**.

Scrapes business leads (law firms, contractors, salons, and other categories) across
city-batch target lists, then exports structured results to CSV and JSON for outreach
and CRM workflows.

Built with AI-assisted development (agent-directed code generation, debugging, and
iteration across multiple versions).

## What it does

- Queries the Google Places API (New) for configurable business categories
- Processes city lists in batches (`cities-b1.txt` ... `cities-b8.txt`)
- Deduplicates results and exports clean lead lists to CSV + JSON
- Designed for repeatable, resumable runs (timestamped output files)

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` (or set the environment variable) with your Google Places API key:

```
GOOGLE_API_KEY=your-key-here
```

## Usage

```powershell
$env:GOOGLE_API_KEY = "your-key-here"
python lead_scraper.py
```

## Notes

- API key is read from the environment — never hardcode keys
- Run outputs (`leads_*.csv`, `leads_*.json`) are gitignored by default
- Places API free-tier friendly; monitor your quota in the Google Cloud console

## License

MIT
