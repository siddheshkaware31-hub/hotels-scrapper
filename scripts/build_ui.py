"""Build rich All-India Dynamic Hotel Scraper UI with 100+ cities, states, and instant filtering."""

import json
from pathlib import Path

hotels_file = Path("data/latest_hotels.json")
cities_file = Path("data/india_cities.json")

if not hotels_file.exists():
    raise FileNotFoundError("data/latest_hotels.json not found")
if not cities_file.exists():
    raise FileNotFoundError("data/india_cities.json not found")

hotels = json.load(open(hotels_file, encoding="utf-8"))
cities = json.load(open(cities_file, encoding="utf-8"))

hotels_json_str = json.dumps(hotels, ensure_ascii=False)
cities_json_str = json.dumps(cities, ensure_ascii=False)

# Collect all distinct states in India from the catalog
states_list = sorted(list({c.get("state", "Other") for c in cities if c.get("state")}))

html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>All-India Hotel Scraper & Analytics Dashboard</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    @keyframes pulse-subtle {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.5; }}
    }}
    .live-dot {{
      animation: pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }}
    .hotel-card {{
      transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    }}
    .hotel-card:hover {{
      transform: translateY(-3px);
      box-shadow: 0 12px 24px -10px rgba(0, 0, 0, 0.15);
    }}
    .tier-chip.active, .state-chip.active {{
      background-color: rgb(5 150 105);
      color: white;
      border-color: transparent;
    }}
  </style>
</head>
<body class="bg-[var(--background)] text-[var(--foreground)] antialiased min-h-screen p-4 md:p-8">

  <div class="max-w-7xl mx-auto space-y-6">

    <!-- Top Master Header -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-6 md:p-8 shadow-sm">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div>
          <div class="flex items-center gap-2.5 mb-2">
            <span class="relative flex h-3 w-3">
              <span class="live-dot absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
            <span class="text-xs font-semibold tracking-wider uppercase text-emerald-500">India National Scraping Engine</span>
            <span id="active-state-badge" class="text-xs text-[var(--muted-foreground)]">• All States</span>
          </div>
          <h1 class="text-2xl md:text-3xl font-bold tracking-tight text-[var(--foreground)]">All-India Hotel Data Explorer</h1>
          <p class="text-sm text-[var(--muted-foreground)] mt-1">
            Access hotel data across all Indian states, union territories, metro hubs, and hill stations.
          </p>
        </div>

        <!-- Action Bar -->
        <div class="flex items-center gap-3 flex-wrap">
          <button id="btn-download-csv" onclick="downloadCSV()" class="inline-flex items-center gap-2 px-4 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm rounded-xl shadow-sm transition-colors cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
            <span id="csv-btn-label">Download India CSV</span>
          </button>
          <button id="btn-download-json" onclick="downloadJSON()" class="inline-flex items-center gap-2 px-4 py-2.5 bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] font-medium text-sm rounded-xl transition-colors cursor-pointer">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4"/></svg>
            Export JSON
          </button>
        </div>
      </div>

      <!-- India Master Filter Controls -->
      <div class="mt-6 pt-6 border-t border-[var(--border)] space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-12 gap-3 items-center">
          
          <!-- State / UT Dropdown -->
          <div class="md:col-span-4">
            <label class="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">State / Union Territory</label>
            <div class="relative">
              <select id="state-select" onchange="onStateSelectChange()" class="w-full bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] text-sm rounded-xl px-3.5 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500 font-medium">
                <option value="all">🇮🇳 All States & Territories</option>
                {"".join(f'<option value="{s}">{s}</option>' for s in states_list)}
              </select>
            </div>
          </div>

          <!-- City Autocomplete / Search Input -->
          <div class="md:col-span-5">
            <label class="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Search Any Indian City</label>
            <div class="relative">
              <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-emerald-500">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              </div>
              <input 
                type="text" 
                id="city-input" 
                list="india-cities-datalist"
                oninput="onCityInputChange()" 
                placeholder="Type any city (e.g. Mumbai, Jaipur, Bengaluru, Goa)..." 
                class="w-full pl-10 pr-10 py-2.5 bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] placeholder-[var(--placeholder)] text-sm rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 font-medium"
              />
              <datalist id="india-cities-datalist">
                {"".join(f'<option value="{c["name"]}">{c["name"]}, {c.get("state", "")}</option>' for c in cities)}
              </datalist>
              <button id="clear-city-btn" onclick="clearCityInput()" class="hidden absolute inset-y-0 right-0 pr-3.5 flex items-center text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
              </button>
            </div>
          </div>

          <!-- City Tier / Category -->
          <div class="md:col-span-3">
            <label class="block text-xs font-semibold text-[var(--muted-foreground)] mb-1">Region Category</label>
            <select id="tier-select" onchange="applyFilters()" class="w-full bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] text-sm rounded-xl px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
              <option value="all">All Categories</option>
              <option value="Tier 1 Metro">Tier 1 Metros</option>
              <option value="Tier 2 Major">Tier 2 Commercial</option>
              <option value="Heritage">Heritage & Tourism</option>
              <option value="Hill Station">Hill Stations</option>
              <option value="Pilgrimage">Pilgrimage & Spiritual</option>
            </select>
          </div>
        </div>

        <!-- Quick Top Cities Badges -->
        <div class="flex items-center gap-2 overflow-x-auto pt-1 pb-1">
          <span class="text-xs text-[var(--muted-foreground)] whitespace-nowrap font-medium">Popular:</span>
          <button onclick="quickPickCity('Mumbai')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Mumbai</button>
          <button onclick="quickPickCity('Delhi')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Delhi</button>
          <button onclick="quickPickCity('Bengaluru')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Bengaluru</button>
          <button onclick="quickPickCity('Jaipur')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Jaipur</button>
          <button onclick="quickPickCity('Goa')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Goa</button>
          <button onclick="quickPickCity('Varanasi')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Varanasi</button>
          <button onclick="quickPickCity('Shimla')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Shimla</button>
          <button onclick="quickPickCity('Kochi')" class="whitespace-nowrap px-3 py-1 text-xs rounded-lg bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer">📍 Kochi</button>
        </div>
      </div>

      <!-- Live Dynamic Metric Stats Strip (Updates per selected City/State) -->
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-[var(--border)]">
        <div class="space-y-1">
          <div class="text-xs font-medium text-[var(--muted-foreground)]">Hotels Displayed</div>
          <div id="stat-count" class="text-2xl font-bold text-[var(--foreground)]">0</div>
        </div>
        <div class="space-y-1">
          <div class="text-xs font-medium text-[var(--muted-foreground)]">Average Rating</div>
          <div id="stat-avg-rating" class="text-2xl font-bold text-amber-500">0.0 ★</div>
        </div>
        <div class="space-y-1">
          <div class="text-xs font-medium text-[var(--muted-foreground)]">Reviews Analyzed</div>
          <div id="stat-reviews" class="text-2xl font-bold text-blue-500">0</div>
        </div>
        <div class="space-y-1">
          <div class="text-xs font-medium text-[var(--muted-foreground)]">Top Rated (4.0+ ★)</div>
          <div id="stat-high-rated" class="text-2xl font-bold text-emerald-500">0</div>
        </div>
      </div>
    </div>

    <!-- Secondary Filters & Search Bar -->
    <div class="bg-[var(--card)] border border-[var(--border)] rounded-2xl p-4 shadow-sm flex flex-col md:flex-row gap-4 items-center justify-between">
      <div class="relative w-full md:w-80">
        <div class="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[var(--muted-foreground)]">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
        </div>
        <input 
          type="text" 
          id="search-input" 
          oninput="applyFilters()"
          placeholder="Filter by hotel title, street, or category..." 
          class="w-full pl-10 pr-4 py-2 bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] placeholder-[var(--placeholder)] text-sm rounded-xl focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-all"
        />
      </div>

      <!-- Rating Pills -->
      <div class="flex items-center gap-2 overflow-x-auto w-full md:w-auto pb-1 md:pb-0">
        <button onclick="setRatingFilter('all')" class="rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-emerald-600 text-white cursor-pointer" data-rating="all">All Ratings</button>
        <button onclick="setRatingFilter('4.5')" class="rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer" data-rating="4.5">4.5+ ★</button>
        <button onclick="setRatingFilter('4.0')" class="rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer" data-rating="4.0">4.0+ ★</button>
        <button onclick="setRatingFilter('website')" class="rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer" data-rating="website">Has Website</button>
        <button onclick="setRatingFilter('phone')" class="rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer" data-rating="phone">Has Phone</button>
      </div>

      <!-- Sort Selector -->
      <div class="flex items-center gap-2 w-full md:w-auto justify-end">
        <span class="text-xs text-[var(--muted-foreground)] whitespace-nowrap">Sort:</span>
        <select id="sort-select" onchange="applyFilters()" class="bg-[var(--background)] border border-[var(--border)] text-[var(--foreground)] text-xs rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500">
          <option value="rating-desc">Highest Rating</option>
          <option value="reviews-desc">Most Reviews</option>
          <option value="name-asc">Name (A - Z)</option>
        </select>
      </div>
    </div>

    <!-- Active Filter Status -->
    <div class="flex items-center justify-between text-xs text-[var(--muted-foreground)] px-1">
      <div>
        Showing <span id="visible-count" class="font-semibold text-[var(--foreground)]">0</span> properties for 
        <span id="active-location-label" class="font-semibold text-emerald-500">All India</span>
      </div>
      <div id="toast-message" class="text-emerald-500 font-medium opacity-0 transition-opacity duration-300">Downloaded successfully!</div>
    </div>

    <!-- Hotels Grid Container -->
    <div id="hotels-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
      <!-- Cards rendered via JavaScript -->
    </div>
  </div>

  <script>
    const HOTELS_DATA = {hotels_json_str};
    const CITIES_DATA = {cities_json_str};
    let activeRatingFilter = 'all';
    let currentFilteredList = [];

    function init() {{
      applyFilters();
    }}

    function quickPickCity(name) {{
      document.getElementById('city-input').value = name;
      document.getElementById('clear-city-btn').classList.remove('hidden');
      
      // Auto-set matching state if known
      const cityObj = CITIES_DATA.find(c => c.name.toLowerCase() === name.toLowerCase());
      if (cityObj && cityObj.state) {{
        document.getElementById('state-select').value = cityObj.state;
      }}
      applyFilters();
    }}

    function onStateSelectChange() {{
      const state = document.getElementById('state-select').value;
      if (state !== 'all') {{
        // Filter cities datalist to only those in the state
        const datalist = document.getElementById('india-cities-datalist');
        const stateCities = CITIES_DATA.filter(c => c.state === state);
        datalist.innerHTML = stateCities.map(c => `<option value="${{c.name}}">${{c.name}}, ${{c.state}}</option>`).join('');
      }}
      applyFilters();
    }}

    function onCityInputChange() {{
      const val = document.getElementById('city-input').value.trim();
      const clearBtn = document.getElementById('clear-city-btn');
      if (val) {{
        clearBtn.classList.remove('hidden');
      }} else {{
        clearBtn.classList.add('hidden');
      }}
      applyFilters();
    }}

    function clearCityInput() {{
      document.getElementById('city-input').value = '';
      document.getElementById('clear-city-btn').classList.add('hidden');
      applyFilters();
    }}

    function setRatingFilter(rating) {{
      activeRatingFilter = rating;
      document.querySelectorAll('.rating-pill').forEach(btn => {{
        if (btn.dataset.rating === rating) {{
          btn.className = 'rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-emerald-600 text-white cursor-pointer';
        }} else {{
          btn.className = 'rating-pill px-3 py-1.5 text-xs font-medium rounded-lg transition-colors bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] cursor-pointer';
        }}
      }});
      applyFilters();
    }}

    function calculateStats(data) {{
      const total = data.length;
      document.getElementById('stat-count').innerText = total;

      const rated = data.filter(h => h.rating && h.rating > 0);
      const avg = rated.length > 0 
        ? (rated.reduce((acc, h) => acc + h.rating, 0) / rated.length).toFixed(1) 
        : '0.0';
      document.getElementById('stat-avg-rating').innerText = avg + ' ★';

      const totalReviews = data.reduce((acc, h) => acc + (h.review_count || 0), 0);
      document.getElementById('stat-reviews').innerText = totalReviews.toLocaleString();

      const highRated = data.filter(h => h.rating && h.rating >= 4.0).length;
      document.getElementById('stat-high-rated').innerText = highRated;
    }}

    function applyFilters() {{
      const selectedState = document.getElementById('state-select').value;
      const cityQuery = document.getElementById('city-input').value.toLowerCase().trim();
      const selectedTier = document.getElementById('tier-select').value;
      const textQuery = document.getElementById('search-input').value.toLowerCase().trim();
      const sortMode = document.getElementById('sort-select').value;

      // Update location labels
      let locLabel = 'All India';
      if (cityQuery) {{
        locLabel = cityQuery.charAt(0).toUpperCase() + cityQuery.slice(1);
      }} else if (selectedState !== 'all') {{
        locLabel = selectedState;
      }}
      document.getElementById('active-state-badge').innerText = `• ${{locLabel}}`;
      document.getElementById('active-location-label').innerText = locLabel;
      document.getElementById('csv-btn-label').innerText = cityQuery ? `Download ${{locLabel}} CSV` : 'Download India CSV';

      // 1. Filter by State & City
      let filtered = HOTELS_DATA.filter(h => {{
        // State check
        if (selectedState !== 'all') {{
          const matchesState = (h.country && h.country.toLowerCase().includes(selectedState.toLowerCase())) ||
                               (h.full_address && h.full_address.toLowerCase().includes(selectedState.toLowerCase()));
          if (!matchesState) return false;
        }}

        // City check
        if (cityQuery) {{
          const inCity = h.city && h.city.toLowerCase().includes(cityQuery);
          const inAddress = h.full_address && h.full_address.toLowerCase().includes(cityQuery);
          if (!inCity && !inAddress) return false;
        }}

        return true;
      }});

      // 2. Filter by Search Query
      if (textQuery) {{
        filtered = filtered.filter(h => {{
          return (h.name && h.name.toLowerCase().includes(textQuery)) ||
                 (h.full_address && h.full_address.toLowerCase().includes(textQuery)) ||
                 (h.category && h.category.toLowerCase().includes(textQuery));
        }});
      }}

      // 3. Filter by Rating Pills
      if (activeRatingFilter === '4.5') filtered = filtered.filter(h => h.rating && h.rating >= 4.5);
      if (activeRatingFilter === '4.0') filtered = filtered.filter(h => h.rating && h.rating >= 4.0);
      if (activeRatingFilter === 'website') filtered = filtered.filter(h => h.website && h.website.length > 0);
      if (activeRatingFilter === 'phone') filtered = filtered.filter(h => h.phone && h.phone.length > 0);

      // 4. Sorting
      if (sortMode === 'rating-desc') {{
        filtered.sort((a, b) => (b.rating || 0) - (a.rating || 0) || (b.review_count || 0) - (a.review_count || 0));
      }} else if (sortMode === 'reviews-desc') {{
        filtered.sort((a, b) => (b.review_count || 0) - (a.review_count || 0));
      }} else if (sortMode === 'name-asc') {{
        filtered.sort((a, b) => (a.name || '').localeCompare(b.name || ''));
      }}

      currentFilteredList = filtered;
      calculateStats(filtered);
      renderCards(filtered, cityQuery, selectedState);
    }}

    function copyCliCommand(cmd) {{
      navigator.clipboard.writeText(cmd);
      showToast('Scraper CLI command copied to clipboard!');
    }}

    function renderCards(hotels, cityQuery, selectedState) {{
      const grid = document.getElementById('hotels-grid');
      document.getElementById('visible-count').innerText = hotels.length;

      if (hotels.length === 0) {{
        const targetCity = cityQuery || (selectedState !== 'all' ? selectedState : 'Jaipur');
        const scrapeCmd = `python -m src.cli scrape --region "${{targetCity}}"`;
        const batchStateCmd = selectedState !== 'all' ? `python -m src.cli scrape-india --state "${{selectedState}}"` : 'python -m src.cli scrape-india --limit 5';

        // Find city info if available in catalog
        const cityMeta = CITIES_DATA.find(c => c.name.toLowerCase() === (cityQuery || '').toLowerCase());

        grid.innerHTML = `
          <div class="col-span-full py-16 px-6 text-center text-[var(--muted-foreground)] bg-[var(--card)] rounded-2xl border border-[var(--border)] shadow-sm space-y-5">
            <div class="w-14 h-14 rounded-2xl bg-emerald-500/10 text-emerald-500 flex items-center justify-center mx-auto text-2xl">
              🇮🇳
            </div>
            <div>
              <p class="font-bold text-lg text-[var(--foreground)]">No local database records yet for "${{targetCity}}"</p>
              ${{cityMeta ? `
                <div class="inline-flex items-center gap-2 mt-2 px-3 py-1 rounded-full bg-[var(--content)] text-xs text-[var(--muted-foreground)]">
                  <span>State: <strong class="text-[var(--foreground)]">${{cityMeta.state}}</strong></span>
                  <span>•</span>
                  <span>Classification: <strong class="text-emerald-500">${{cityMeta.tier}}</strong></span>
                  <span>•</span>
                  <span>Coordinates: ${{cityMeta.lat}}, ${{cityMeta.lng}}</span>
                </div>
              ` : ''}}
              <p class="text-xs text-[var(--muted-foreground)] mt-3 max-w-lg mx-auto leading-relaxed">
                You can launch the automated Playwright scraper to extract all hotels in <strong>${{targetCity}}</strong> right now with resilient selectors, deduplication, and full address metadata:
              </p>
            </div>
            <div class="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
              <div class="inline-flex items-center gap-2 px-4 py-2.5 bg-[var(--content)] border border-[var(--border)] rounded-xl text-xs font-mono text-emerald-500 shadow-inner">
                <span>${{scrapeCmd}}</span>
                <button onclick="copyCliCommand('${{scrapeCmd}}')" class="p-1 hover:text-[var(--foreground)] text-[var(--muted-foreground)] cursor-pointer" title="Copy command">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3"/></svg>
                </button>
              </div>
            </div>
            <p class="text-[11px] text-[var(--muted-foreground)]">
              Tip: Or batch scrape all cities in this state with: <code class="font-mono text-emerald-600 bg-[var(--content)] px-1.5 py-0.5 rounded">${{batchStateCmd}}</code>
            </p>
          </div>
        `;
        return;
      }}

      grid.innerHTML = hotels.map(h => {{
        const photo = (h.photo_urls && h.photo_urls.length > 0) ? h.photo_urls[0] : null;
        const rating = h.rating ? h.rating.toFixed(1) : 'N/A';
        const reviews = h.review_count ? h.review_count.toLocaleString() : '0';
        const price = h.price_level || 'Price not listed';

        return `
          <div class="hotel-card bg-[var(--card)] border border-[var(--border)] rounded-2xl overflow-hidden flex flex-col shadow-sm">
            <!-- Card Thumbnail -->
            <div class="h-44 w-full bg-[var(--content)] relative overflow-hidden">
              ${{photo ? `
                <img src="${{photo}}\" alt="${{h.name}}\" class=\"w-full h-full object-cover transition-transform duration-500 hover:scale-105\" loading=\"lazy\" />
              ` : `
                <div class=\"w-full h-full flex flex-col items-center justify-center text-[var(--muted-foreground)] gap-2 bg-gradient-to-br from-[var(--content)] to-[var(--border)]\">
                  <svg class=\"w-8 h-8 opacity-40\" fill=\"none\" stroke=\"currentColor\" viewBox=\"0 0 24 24\"><path stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4\"/></svg>
                  <span class=\"text-xs font-medium\">Hotel View</span>
                </div>
              `}}
              <div class=\"absolute top-3 right-3 bg-black/75 backdrop-blur-md px-2.5 py-1 rounded-full text-xs font-bold text-amber-400 flex items-center gap-1 shadow-sm\">
                <span>★</span>
                <span>${{rating}}</span>
                <span class=\"text-[10px] text-white/80 font-normal\">(${{reviews}})</span>
              </div>
              <div class=\"absolute bottom-3 left-3 bg-black/60 backdrop-blur-md px-2.5 py-1 rounded-lg text-xs font-medium text-white shadow-sm\">
                ${{price}}
              </div>
            </div>

            <!-- Card Body -->
            <div class=\"p-5 flex-1 flex flex-col justify-between space-y-4\">
              <div>
                <div class=\"flex items-center justify-between gap-2\">
                  <div class=\"text-xs font-medium text-emerald-500 uppercase tracking-wide truncate\">${{h.category || 'Hotel'}}</div>
                  <div class=\"text-[11px] font-semibold text-[var(--muted-foreground)] px-2 py-0.5 rounded-md bg-[var(--content)] shrink-0\">${{h.city || 'India'}}</div>
                </div>
                <h3 class=\"text-base font-bold text-[var(--foreground)] mt-1 line-clamp-1\" title=\"${{h.name}}\">${{h.name}}</h3>
                <p class=\"text-xs text-[var(--muted-foreground)] mt-2 line-clamp-2 leading-relaxed\">
                  ${{h.full_address || 'Address not listed'}}
                </p>
              </div>

              <!-- Contact & Actions -->
              <div class=\"pt-3 border-t border-[var(--border)] space-y-3\">
                <div class=\"flex items-center justify-between text-xs text-[var(--muted-foreground)]\">
                  <span class=\"flex items-center gap-1.5 truncate max-w-[180px]\">
                    <svg class=\"w-3.5 h-3.5 shrink-0\" fill=\"none\" stroke=\"currentColor\" viewBox=\"0 0 24 24\"><path stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"2\" d=\"M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z\"/></svg>
                    <span class=\"truncate\">${{h.phone || 'No phone'}}</span>
                  </span>
                  ${{h.website ? `
                    <a href=\"${{h.website}}\" target=\"_blank\" rel=\"noopener noreferrer\" class=\"text-emerald-500 hover:text-emerald-400 font-medium inline-flex items-center gap-1 hover:underline\">
                      Website ↗
                    </a>
                  ` : '<span class=\"text-[var(--muted-foreground)]/60\">No site</span>'}}
                </div>

                <a href=\"${{h.google_maps_url}}\" target=\"_blank\" rel=\"noopener noreferrer\" class=\"w-full py-2 px-3 text-xs font-medium text-center rounded-xl bg-[var(--content)] hover:bg-[var(--border)] text-[var(--foreground)] border border-[var(--border)] flex items-center justify-center gap-1.5 transition-colors\">
                  <svg class=\"w-3.5 h-3.5 text-red-500\" fill=\"currentColor\" viewBox=\"0 0 24 24\"><path d=\"M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5a2.5 2.5 0 010-5 2.5 2.5 0 010 5z\"/></svg>
                  View on Google Maps
                </a>
              </div>
            </div>
          </div>
        `;
      }}).join('');
    }}

    function showToast(text) {{
      const toast = document.getElementById('toast-message');
      toast.innerText = text;
      toast.classList.remove('opacity-0');
      setTimeout(() => {{
        toast.classList.add('opacity-0');
      }}, 3000);
    }}

    function downloadCSV() {{
      const cityQuery = document.getElementById('city-input').value.trim();
      const selectedState = document.getElementById('state-select').value;
      let labelSlug = 'india_all';
      if (cityQuery) {{
        labelSlug = cityQuery.toLowerCase().replace(/[^a-z0-9]/g, '_');
      }} else if (selectedState !== 'all') {{
        labelSlug = selectedState.toLowerCase().replace(/[^a-z0-9]/g, '_');
      }}

      const exportList = currentFilteredList.length > 0 ? currentFilteredList : HOTELS_DATA;

      const headers = [
        'place_id', 'name', 'category', 'full_address', 'city', 'country',
        'rating', 'review_count', 'price_level', 'phone', 'website',
        'google_maps_url', 'scraped_at'
      ];

      function escapeCell(val) {{
        if (val === null || val === undefined) return '""';
        let s = String(val);
        if (['=', '+', '-', '@', '\\t', '\\r'].includes(s[0])) {{
          s = "'" + s;
        }}
        return '"' + s.replace(/"/g, '""') + '"';
      }}

      const rows = [headers.join(',')];
      exportList.forEach(h => {{
        const row = [
          escapeCell(h.place_id),
          escapeCell(h.name),
          escapeCell(h.category),
          escapeCell(h.full_address),
          escapeCell(h.city),
          escapeCell(h.country),
          escapeCell(h.rating),
          escapeCell(h.review_count),
          escapeCell(h.price_level),
          escapeCell(h.phone),
          escapeCell(h.website),
          escapeCell(h.google_maps_url),
          escapeCell(h.scraped_at)
        ];
        rows.push(row.join(','));
      }});

      const csvContent = '\\uFEFF' + rows.join('\\r\\n');
      const blob = new Blob([csvContent], {{ type: 'text/csv;charset=utf-8;' }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', `hotels_${{labelSlug}}_report_${{new Date().toISOString().slice(0,10)}}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      showToast(`Downloaded CSV for ${{labelSlug.replace(/_/g, ' ')}}!`);
    }}

    function downloadJSON() {{
      const cityQuery = document.getElementById('city-input').value.trim();
      const selectedState = document.getElementById('state-select').value;
      let labelSlug = 'india_all';
      if (cityQuery) {{
        labelSlug = cityQuery.toLowerCase().replace(/[^a-z0-9]/g, '_');
      }} else if (selectedState !== 'all') {{
        labelSlug = selectedState.toLowerCase().replace(/[^a-z0-9]/g, '_');
      }}

      const exportList = currentFilteredList.length > 0 ? currentFilteredList : HOTELS_DATA;
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(exportList, null, 2));
      const link = document.createElement('a');
      link.setAttribute('href', dataStr);
      link.setAttribute('download', `hotels_${{labelSlug}}_report_${{new Date().toISOString().slice(0,10)}}.json`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      showToast(`Exported JSON for ${{labelSlug.replace(/_/g, ' ')}}!`);
    }}

    window.onload = init;
  </script>
</body>
</html>
"""

artifact_dir = Path(r"C:\Users\ASUS\.gemini\antigravity\brain\bb445c36-8e9a-4c85-aa84-95bfe82b67a7")
artifact_dir.mkdir(parents=True, exist_ok=True)
target_path = artifact_dir / "hotel_dashboard.html"
target_path.write_text(html_content, encoding="utf-8")
print(f"Successfully generated All-India dynamic UI artifact at {target_path}")
