import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import folium
from folium.plugins import BeautifyIcon
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation
import re
import json
import os
from geopy.geocoders import Nominatim
from concurrent.futures import ThreadPoolExecutor, as_completed

LOCATION = get_geolocation()

# Set page config
st.set_page_config(page_title="Tabelog Top 100 Map", page_icon="🍽️", layout="wide")

# Custom headers to mimic browser request
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.7,en;q=0.3",
}

# Cache file path
CACHE_FILE = "tabelog_cache.json"


def load_cache():
    """Load cached data from JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache):
    """Save cache data to JSON file."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except IOError as e:
        st.warning(f"Could not save cache: {e}")


@st.cache_data(ttl=3600)
def get_restaurant_links(award_url):
    """Fetch restaurant links from a Tabelog award page."""
    restaurants = []

    try:
        response = requests.get(award_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Find all restaurant links - they follow the pattern tabelog.com/{prefecture}/...
        # Restaurant links are in anchor tags with href containing tabelog.com and restaurant IDs
        links = soup.find_all(
            "a", href=re.compile(r"https://tabelog\.com/[a-z]+/A\d+/A\d+/\d+")
        )

        seen_urls = set()
        for link in links:
            url = link.get("href", "")
            # Clean URL (remove trailing slashes and query params)
            url = url.rstrip("/").split("?")[0] + "/"

            # Skip if already seen or if it's not a restaurant detail page
            if url in seen_urls or not re.match(
                r"https://tabelog\.com/[a-z]+/A\d+/A\d+/\d+/$", url
            ):
                continue

            # Convert to English version by adding /en/ after tabelog.com
            url = re.sub(r"https://tabelog\.com/", "https://tabelog.com/en/", url)

            seen_urls.add(url)

            # Get restaurant name from link text or nested elements
            name = link.get_text(strip=True)
            if not name:
                name_elem = link.find(["span", "div", "p"])
                if name_elem:
                    name = name_elem.get_text(strip=True)

            if name and url:
                restaurants.append({"name": name, "url": url})

    except Exception as e:
        st.error(f"Error fetching award page: {e}")

    return restaurants


def _fetch_restaurant_details(url):
    """Fetch detailed information about a restaurant (non-cached, thread-safe)."""
    details = {
        "url": url,
        "name": "",
        "address": "",
        "transportation": "",
        "genre": "",
        "rating": "",
        "price_dinner": "",
        "price_lunch": "",
        "phone": "",
        "hours": "",
        "reservation": "",
        "latitude": None,
        "longitude": None,
    }

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        html_text = response.text
        soup = BeautifulSoup(html_text, "html.parser")

        # Extract coordinates directly from page (embedded in JSON)
        lat_match = re.search(r'"latitude"\s*:\s*([0-9.]+)', html_text)
        lon_match = re.search(r'"longitude"\s*:\s*([0-9.]+)', html_text)
        if lat_match and lon_match:
            details["latitude"] = float(lat_match.group(1))
            details["longitude"] = float(lon_match.group(1))

        # Get restaurant name
        name_elem = soup.find("h2", class_="display-name")
        if name_elem:
            name_span = name_elem.find("span")
            if name_span:
                details["name"] = name_span.get_text(strip=True)
            else:
                details["name"] = name_elem.get_text(strip=True).split("（")[0].strip()

        # Alternative name extraction
        if not details["name"]:
            title = soup.find("title")
            if title:
                details["name"] = title.get_text().split(" - ")[0].strip()

        # Get rating
        rating_elem = soup.find("b", class_="c-rating__val")
        if rating_elem:
            details["rating"] = rating_elem.get_text(strip=True)
        else:
            rating_elem = soup.find("span", class_="rdheader-rating__score-val-dtl")
            if rating_elem:
                details["rating"] = rating_elem.get_text(strip=True)

        # Get address from table
        address_row = soup.find("th", string=re.compile("Address"))
        if address_row:
            address_td = address_row.find_next_sibling("td")
            if address_td:
                address_text = address_td.get_text(separator=" ", strip=True)
                address_text = re.sub(r"\s*-\s*地図.*", "", address_text)
                address_text = re.sub(r"\s*Show larger map.*", "", address_text)
                address_text = re.sub(r"\s*Find nearby restaurants.*", "", address_text)
                details["address"] = address_text.strip()

        # Get transportation/access info
        transportation_row = soup.find("th", string=re.compile("Transportation"))
        if transportation_row:
            transportation_td = transportation_row.find_next_sibling("td")
            if transportation_td:
                details["transportation"] = transportation_td.get_text(strip=True)

        # Get genre
        genre_row = soup.find("th", string=re.compile("Categories"))
        if genre_row:
            genre_td = genre_row.find_next_sibling("td")
            if genre_td:
                details["genre"] = genre_td.get_text(strip=True)

        # Get phone
        phone_row = soup.find("th", string=re.compile("Phone number"))
        if phone_row:
            phone_td = phone_row.find_next_sibling("td")
            if phone_td:
                details["phone"] = phone_td.get_text(strip=True)

        # Get reservation availability
        reservation_row = soup.find("th", string=re.compile("Reservation availability"))
        if reservation_row:
            reservation_td = reservation_row.find_next_sibling("td")
            if reservation_td:
                reservation_text = reservation_td.get_text(strip=True)
                # Just get the first part (e.g., "Reservations available")
                details["reservation"] = reservation_text.split("■")[0].strip()[:50]

        # Get hours
        hours_row = soup.find("th", string=re.compile("Business hours"))
        if hours_row:
            hours_td = hours_row.find_next_sibling("td")
            if hours_td:
                details["hours"] = hours_td.get_text(strip=True)[:100]

        # Get average price from table
        price_row = soup.find("th", string=re.compile("Average price"))
        if price_row:
            price_td = price_row.find_next_sibling("td")
            if price_td:
                price_text = price_td.get_text(strip=True)
                # Try format with Dinner/Lunch labels first
                dinner_match = re.search(
                    r"Dinner\s*(JPY\s*[\d,]+\s*-\s*JPY\s*[\d,]+)", price_text
                )
                if dinner_match:
                    details["price_dinner"] = dinner_match.group(1)
                lunch_match = re.search(
                    r"Lunch\s*(JPY\s*[\d,]+\s*-\s*JPY\s*[\d,]+)", price_text
                )
                if lunch_match:
                    details["price_lunch"] = lunch_match.group(1)

                # If no labels found, try to extract two price ranges
                # Format: "JPY 4,000 - JPY 4,999JPY 1,000 - JPY 1,999" (dinner then lunch)
                if not details["price_dinner"] and not details["price_lunch"]:
                    price_ranges = re.findall(
                        r"(JPY\s*[\d,]+\s*-\s*JPY\s*[\d,]+)", price_text
                    )
                    if len(price_ranges) >= 2:
                        details["price_dinner"] = price_ranges[0]
                        details["price_lunch"] = price_ranges[1]
                    elif len(price_ranges) == 1:
                        details["price_dinner"] = price_ranges[0]

    except Exception:
        pass  # Silently fail for thread safety

    return details


def _geocode_address(restaurant):
    """Geocode an address to get latitude and longitude (non-cached, thread-safe).
    This is a fallback for when coordinates aren't embedded in the Tabelog page."""
    address = restaurant.get("address", "")
    transportation = restaurant.get("transportation", "")

    if not address and not transportation:
        return None, None

    try:
        geolocator = Nominatim(user_agent="tabelog_map_app_v3")

        # Try with transportation info first (often has station name which is more reliable)
        if transportation:
            # Extract station name from transportation info
            # e.g., "Tōkyū Ikegami Line, Mitakiyama Station, 2 minutes on foot"
            station_match = re.search(
                r"([A-Za-z\-]+(?:\s+[A-Za-z\-]+)*)\s*(?:Station|Sta\.)", transportation
            )
            if station_match:
                station_name = station_match.group(1) + " Station"
                location = geolocator.geocode(
                    station_name + ", Tokyo, Japan", timeout=10
                )
                if location:
                    return location.latitude, location.longitude

        if address:
            # Clean the address
            clean_address = address.strip()
            clean_address = re.sub(
                r"\s+(THE\s+|ザ\s+).*$", "", clean_address, flags=re.IGNORECASE
            )

            # Try with full address first
            location = geolocator.geocode(clean_address + ", Japan", timeout=10)
            if location:
                return location.latitude, location.longitude

            # Try prefecture + ward + district
            prefecture_match = re.search(
                r"(東京都|大阪府|京都府|北海道|.{2,3}県)", clean_address
            )
            ward_match = re.search(r"(.{1,4}区|.{1,4}市)", clean_address)
            district_match = re.search(r"(区|市)(.{1,6}?)\d", clean_address)

            if prefecture_match and ward_match:
                # Try with district if available
                if district_match:
                    simplified = (
                        prefecture_match.group(1)
                        + ward_match.group(1)
                        + district_match.group(2)
                    )
                    location = geolocator.geocode(simplified + ", Japan", timeout=10)
                    if location:
                        return location.latitude, location.longitude

                # Try just prefecture + ward
                simplified = prefecture_match.group(1) + ward_match.group(1)
                location = geolocator.geocode(simplified + ", Japan", timeout=10)
                if location:
                    return location.latitude, location.longitude

    except Exception:
        pass  # Silently fail for thread safety

    return None, None


def create_map(restaurants_df, current_location=None):
    """Create a Folium map with restaurant markers.

    Args:
        restaurants_df: DataFrame with restaurant data
        current_location: tuple of (latitude, longitude) for user's current location
    """
    # Convert rating to numeric and sort by rating descending (before filtering)
    df_sorted = restaurants_df.copy()
    df_sorted["rating_numeric"] = pd.to_numeric(df_sorted["rating"], errors="coerce")
    df_sorted = df_sorted.sort_values("rating_numeric", ascending=False).reset_index(
        drop=True
    )

    # Assign rank before filtering (1-based)
    df_sorted["rank"] = range(1, len(df_sorted) + 1)

    # Filter restaurants with valid coordinates (keeping original rank)
    valid_df = df_sorted.dropna(subset=["latitude", "longitude"]).copy()

    # Determine map center - use current location if available, otherwise default to Tokyo
    map_center = [35.6852, 139.7528]

    if valid_df.empty:
        st.warning("No restaurants could be geocoded. Showing default map.")
        m = folium.Map(location=map_center, zoom_start=11, tiles=None)
        folium.TileLayer("CartoDB Voyager", name="CartoDB Voyager").add_to(m)
        # Add current location marker even if no restaurants
        if current_location:
            folium.Marker(
                location=[current_location[0], current_location[1]],
                popup="📍 You are here",
                tooltip="Your current location",
                icon=folium.Icon(color="blue", icon="user", prefix="fa"),
            ).add_to(m)
        folium.LayerControl().add_to(m)
        return m

    # Create map with no default tiles
    m = folium.Map(location=map_center, zoom_start=12, tiles=None)

    # Add multiple tile layers for user to choose from
    folium.TileLayer("OpenStreetMap", name="OpenStreetMap").add_to(m)
    folium.TileLayer("CartoDB positron", name="CartoDB Positron (Light)").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="CartoDB Dark Matter").add_to(m)
    folium.TileLayer("CartoDB Voyager", name="CartoDB Voyager").add_to(m)

    # Add markers for each restaurant (using pre-assigned rank)
    for idx, row in valid_df.iterrows():
        rank = row["rank"]
        # Create popup content
        popup_html = f"""
        <div style="width: 300px; font-family: Arial, sans-serif;">
            <h4 style="margin: 0 0 10px 0; color: #d32323;">#{rank} {row['name']}</h4>
            <p style="margin: 5px 0;"><strong>Rating:</strong> ⭐ {row.get('rating', 'N/A')}</p>
            <p style="margin: 5px 0;"><strong>Genre:</strong> {row.get('genre', 'N/A')}</p>
            <p style="margin: 5px 0;"><strong>Reservation details:</strong> {row.get('reservation', 'N/A')}</p>
            <p style="margin: 5px 0;"><strong>Price (Lunch):</strong> {row.get('price_lunch', 'N/A')}</p>
            <p style="margin: 5px 0;"><strong>Price (Dinner):</strong> {row.get('price_dinner', 'N/A')}</p>
            <p style="margin: 10px 0 0 0;"><a href="{row['url']}" target="_blank">View on Tabelog →</a></p>
        </div>
        """

        # Create BeautifyIcon with rank number
        icon = BeautifyIcon(
            icon="cutlery",
            icon_shape="marker",
            number=rank,
            border_color="#d32323",
            background_color="#ffffff",
            text_color="#d32323",
            prefix="fa",
            icon_size=(35, 35),
        )

        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=folium.Popup(popup_html, max_width=350),
            tooltip=f"#{rank} {row['name']}",
            icon=icon,
        ).add_to(m)

    # Add current location marker if available
    if current_location:
        folium.Marker(
            location=[current_location[0], current_location[1]],
            popup="📍 You are here",
            tooltip="Your current location",
            icon=folium.Icon(color="blue", icon="user", prefix="fa"),
        ).add_to(m)

    # Add layer control for switching map styles
    folium.LayerControl().add_to(m)

    return m


def main():
    # Sidebar with award categories
    with st.sidebar:
        st.header("🏆 Award Categories")

        # All Tabelog Hyakumeiten categories in order from website
        # Using Tokyo where available, otherwise East (for Tokyo area)
        example_urls = {
            "🍱 Tokyo Top 100": "https://award.tabelog.com/hyakumeiten/japanese_tokyo?pref=tokyo",
            "🍜 Ramen Tokyo": "https://award.tabelog.com/hyakumeiten/ramen_tokyo?pref=tokyo",
            "🍢 Yakitori East": "https://award.tabelog.com/hyakumeiten/yakitori_east?pref=tokyo",
            "🐔 Chicken Dishes": "https://award.tabelog.com/hyakumeiten/toriryori?pref=tokyo",
            "🥩 Yakiniku Tokyo": "https://award.tabelog.com/hyakumeiten/yakiniku_tokyo?pref=tokyo",
            "🍺 Izakaya East": "https://award.tabelog.com/hyakumeiten/izakaya_east?pref=tokyo",
            "🍶 Standing Bar": "https://award.tabelog.com/hyakumeiten/tachinomi?pref=tokyo",
            "🥞 Okonomiyaki": "https://award.tabelog.com/hyakumeiten/okonomiyaki?pref=tokyo",
            "🥩 Steak East": "https://award.tabelog.com/hyakumeiten/steak_east?pref=tokyo",
            "🍜 Soba East": "https://award.tabelog.com/hyakumeiten/soba_east?pref=tokyo",
            "☕ Cafe East": "https://award.tabelog.com/hyakumeiten/cafe_east?pref=tokyo",
            "🍛 Yoshoku East": "https://award.tabelog.com/hyakumeiten/yoshoku_east?pref=tokyo",
            "🇫🇷 French Tokyo": "https://award.tabelog.com/hyakumeiten/french_tokyo?pref=tokyo",
            "🎨 Creative/Innovative": "https://award.tabelog.com/hyakumeiten/creative_innovative?pref=tokyo",
            "🇮🇹 Italian Tokyo": "https://award.tabelog.com/hyakumeiten/italian_tokyo?pref=tokyo",
            "🍕 Pizza": "https://award.tabelog.com/hyakumeiten/pizza?pref=tokyo",
            "🍤 Tempura": "https://award.tabelog.com/hyakumeiten/tempura?pref=tokyo",
            "🍣 Sushi Tokyo": "https://award.tabelog.com/hyakumeiten/sushi_tokyo?pref=tokyo",
            "🍚 Shokudo": "https://award.tabelog.com/hyakumeiten/shokudo?pref=tokyo",
            "🍲 Sukiyaki/Shabu-shabu": "https://award.tabelog.com/hyakumeiten/sukiyaki_shabushabu?pref=tokyo",
            "🇪🇸 Spanish": "https://award.tabelog.com/hyakumeiten/spanish?pref=tokyo",
            "🍛 Curry Tokyo": "https://award.tabelog.com/hyakumeiten/curry_tokyo?pref=tokyo",
            "🍜 Asian/Ethnic Tokyo": "https://award.tabelog.com/hyakumeiten/asia_ethnic_tokyo?pref=tokyo",
            "🐟 Unagi": "https://award.tabelog.com/hyakumeiten/unagi?pref=tokyo",
            "🥟 Gyoza": "https://award.tabelog.com/hyakumeiten/gyoza?pref=tokyo",
            "🥡 Chinese Tokyo": "https://award.tabelog.com/hyakumeiten/chinese_tokyo?pref=tokyo",
            "🍗 Tonkatsu": "https://award.tabelog.com/hyakumeiten/tonkatsu?pref=tokyo",
            "🍔 Hamburger": "https://award.tabelog.com/hyakumeiten/hamburger?pref=tokyo",
            "🍜 Udon East": "https://award.tabelog.com/hyakumeiten/udon_east?pref=tokyo",
            "🍡 Wagashi Tokyo": "https://award.tabelog.com/hyakumeiten/wagashi_tokyo?pref=tokyo",
            "🍰 Sweets Tokyo": "https://award.tabelog.com/hyakumeiten/sweets_tokyo?pref=tokyo",
            "🍦 Ice Cream/Gelato": "https://award.tabelog.com/hyakumeiten/ice_gelato?pref=tokyo",
            "🍸 Bar": "https://award.tabelog.com/hyakumeiten/bar?pref=tokyo",
            "🍞 Bread Tokyo": "https://award.tabelog.com/hyakumeiten/bread_tokyo?pref=tokyo",
            "☕ Kissaten": "https://award.tabelog.com/hyakumeiten/kissaten?pref=tokyo",
        }

        # Initialize session state for URL if not exists
        if "selected_url" not in st.session_state:
            st.session_state["selected_url"] = (
                "https://award.tabelog.com/hyakumeiten/japanese_tokyo?pref=tokyo"
            )

        for label, example_url in example_urls.items():
            if st.button(label, key=f"sidebar_{label}", use_container_width=True):
                st.session_state["selected_url"] = example_url

        st.divider()
        st.markdown(
            """
            🔗 [Browse all Tabelog categories](https://award.tabelog.com/hyakumeiten)
            """,
        )

    st.title("🍽 Tabelog Top 100 Restaurant Map")
    st.markdown(
        """
        Select a **top 100 category** in the sidebar or enter a Tabelog Hyakumeiten (百名店) award page URL to visualize all restaurants on a map.
        
        👉  [Browse all Tabelog categories](https://award.tabelog.com/hyakumeiten)
        """
    )

    # URL input
    url = st.text_input("Tabelog Category URL:", value=st.session_state["selected_url"])

    # Load cache
    cache = load_cache()

    # Check if we have cached data for this URL
    col1, col2 = st.columns(2)
    with col1:
        fetch_fresh = st.button(
            "🔍 Fetch Restaurants", type="primary", use_container_width=True
        )
    with col2:
        use_cached = (
            st.button("📦 Load from Cache", use_container_width=True)
            if url in cache
            else False
        )

    if url in cache:
        st.info(
            f"📦 Cached data available for this URL ({len(cache[url])} restaurants)"
        )

    if use_cached and url in cache:
        # Load from cache
        detailed_restaurants = cache[url]
        df = pd.DataFrame(detailed_restaurants)
        st.session_state["restaurants_df"] = df
        st.success(f"Loaded {len(detailed_restaurants)} restaurants from cache!")

    if fetch_fresh:
        if not url:
            st.error("Please enter a valid URL")
            return

        with st.spinner("Fetching restaurant list..."):
            restaurants = get_restaurant_links(url)

        if not restaurants:
            st.error("No restaurants found. Please check the URL.")
            return

        st.success(f"Found {len(restaurants)} restaurants!")

        # Fetch details for each restaurant
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Parallel fetch restaurant details
        status_text.text("Fetching restaurant details in parallel...")
        detailed_restaurants = [None] * len(restaurants)

        def fetch_with_index(args):
            idx, rest = args
            details = _fetch_restaurant_details(rest["url"])
            if not details["name"]:
                details["name"] = rest["name"]
            return idx, details

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {
                executor.submit(fetch_with_index, (i, rest)): i
                for i, rest in enumerate(restaurants)
            }
            completed = 0
            for future in as_completed(futures):
                idx, details = future.result()
                detailed_restaurants[idx] = details
                completed += 1
                progress_bar.progress(completed / len(restaurants))

        # Geocode only restaurants missing coordinates (fallback)
        missing_coords = [
            (i, r)
            for i, r in enumerate(detailed_restaurants)
            if r.get("latitude") is None or r.get("longitude") is None
        ]

        if missing_coords:
            status_text.text(
                f"Geocoding {len(missing_coords)} addresses without embedded coordinates..."
            )

            def geocode_with_index(args):
                idx, rest = args
                lat, lon = _geocode_address(rest)
                return idx, lat, lon

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {
                    executor.submit(geocode_with_index, (i, rest)): i
                    for i, rest in missing_coords
                }
                completed = 0
                for future in as_completed(futures):
                    idx, lat, lon = future.result()
                    detailed_restaurants[idx]["latitude"] = lat
                    detailed_restaurants[idx]["longitude"] = lon
                    completed += 1
                    progress_bar.progress(completed / len(missing_coords))

        status_text.empty()
        progress_bar.empty()

        # Save to cache
        cache[url] = detailed_restaurants
        save_cache(cache)
        st.success("💾 Data saved to cache!")

        # Create DataFrame
        df = pd.DataFrame(detailed_restaurants)

        # Store in session state
        st.session_state["restaurants_df"] = df

    # Display results if available
    if "restaurants_df" in st.session_state:
        df = st.session_state["restaurants_df"]

        st.subheader("📍 Restaurant Map")

        # Get current location from browser
        current_location = None
        if LOCATION and "coords" in LOCATION:
            current_location = (
                LOCATION["coords"]["latitude"],
                LOCATION["coords"]["longitude"],
            )

        # Create and display map (layer control is built into the map)
        m = create_map(df, current_location=current_location)
        st_folium(m, width=None, height=600, use_container_width=True)

        # Show statistics
        valid_count = df.dropna(subset=["latitude", "longitude"]).shape[0]
        st.info(f"📊 Showing {valid_count} of {len(df)} restaurants on the map.")

        # Display data table
        st.subheader("📋 Restaurant List")

        # Select columns to display
        display_cols = [
            "name",
            "rating",
            "genre",
            "price_lunch",
            "price_dinner",
            "address",
            "url",
            "transportation",
            "reservation",
            "latitude",
            "longitude",
        ]
        display_cols = [c for c in display_cols if c in df.columns]

        # Sort by rating descending
        df_display = df[display_cols].copy()
        df_display["rating_sort"] = pd.to_numeric(df_display["rating"], errors="coerce")
        df_display = df_display.sort_values("rating_sort", ascending=False).drop(
            columns=["rating_sort"]
        )
        df_display.insert(0, "rank", range(1, len(df_display) + 1))

        st.dataframe(
            df_display,
            hide_index=True,
            use_container_width=True,
            column_config={
                "url": st.column_config.LinkColumn("Tabelog Link"),
                "rating": st.column_config.NumberColumn("Rating", format="%.2f"),
            },
        )

        # Download option
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name="tabelog_restaurants.csv",
            mime="text/csv",
        )


if __name__ == "__main__":
    main()
