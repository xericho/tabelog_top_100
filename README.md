# Tabelog Top 100 Restaurant Map 

A Streamlit app that visualizes Tabelog's Hyakumeiten (百名店 / Top 100) award-winning restaurants on an interactive map.

## Features

- 📍 Parse restaurant links from any Tabelog Hyakumeiten award page
- 🔍 Fetch detailed restaurant information (rating, price, hours, reservation availability, etc.)
- 🗺️ Display all restaurants on an interactive Folium map with switchable map styles
- 🏆 Ranked markers showing restaurant position by rating
- 💾 JSON caching to avoid re-fetching data
- ⚡ Parallel fetching for faster data retrieval
- 📥 Export data to CSV

## Installation

### Option 1: Docker (Recommended)

```bash
# Build the image
docker build -t tabelog-map .

# Run the container
docker run -p 8501:8501 tabelog-map
```

To persist the cache between container restarts:
```bash
docker run -p 8501:8501 -v $(pwd)/tabelog_cache.json:/app/tabelog_cache.json tabelog-map
```

Then open http://localhost:8501 in your browser.

### Option 2: Local Python

1. Create a virtual environment (recommended):
```bash
python -m venv .venv
source .venv/bin/activate  # On macOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Run the Streamlit app:
```bash
streamlit run app.py
```

2. Use the quick select buttons or enter a Tabelog award URL manually:
   - 🍕 Pizza Tokyo
   - 🍶 Standing Drinking Tokyo
   - 🥩 Steak East/West
   - 🍜 Ramen Tokyo
   - 🍛 Curry Tokyo

3. Click "🔍 Fetch Restaurants" to scrape fresh data, or "📦 Load from Cache" if available
4. View the restaurants on the interactive map!

## Map Features

- **Numbered markers**: Each marker shows the restaurant's rank (sorted by rating)
- **Layer control**: Switch between map styles (CartoDB Voyager, OpenStreetMap, CartoDB Positron, CartoDB Dark Matter) using the control in the top-right corner
- **Popup info**: Click any marker to see restaurant details including rating, genre, prices, and reservation info
- **Accurate coordinates**: Extracted directly from Tabelog pages (with geocoding fallback)

## Restaurant Details

Each restaurant card shows:
- Restaurant name and rank
- Rating (⭐)
- Genre/Categories
- Lunch & Dinner price ranges
- Reservation availability
- Direct link to Tabelog page

## Caching

- Data is cached to `tabelog_cache.json` keyed by award URL
- Use "Load from Cache" to quickly reload previously fetched data
- Use "Fetch Restaurants" to get fresh data and update the cache

## Technologies Used

- **Streamlit**: Web application framework
- **BeautifulSoup4**: HTML parsing
- **Folium**: Interactive maps with BeautifyIcon markers
- **Geopy**: Fallback geocoding for addresses
- **Pandas**: Data manipulation
- **ThreadPoolExecutor**: Parallel data fetching

## Disclaimer

This tool is for personal use only. Please respect Tabelog's terms of service and avoid excessive scraping.
