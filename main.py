"""
Weather Tracking Dashboard with History Storage
================================================
A professional Python application for tracking real-time weather data
and storing historical records for analysis.

Requirements:
    pip install requests matplotlib

Usage:
    python weather_dashboard.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import requests
import json
import csv
import os
import threading
import time
from datetime import datetime
from collections import defaultdict

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# ──────────────────────────────────────────────
# Configuration & Constants
# ──────────────────────────────────────────────
API_BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
CONFIG_PATH = "api_config.json"
AUTO_REFRESH_SEC = 300  # 5 minutes

COLORS = {
    "bg_dark":    "#1a1a2e",
    "bg_medium":  "#16213e",
    "bg_light":   "#0f3460",
    "accent":     "#e94560",
    "accent_hov": "#ff6b81",
    "text_pri":   "#ffffff",
    "text_sec":   "#a0a0c0",
    "success":    "#00d2d3",
    "warning":    "#ffa502",
    "danger":     "#ff4757",
    "info":       "#54a0ff",
    "card":       "#1e2a4a",
}


# ══════════════════════════════════════════════
# MODULE 1: Weather API
# ══════════════════════════════════════════════
class WeatherAPI:
    """Fetches and parses weather data from OpenWeatherMap."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = API_BASE_URL

    def fetch_weather(self, city: str):
        """
        Fetch current weather for *city*.
        Returns tuple: (data_dict, None) on success, (None, error_msg) on failure.
        """
        if not self.api_key:
            return None, "API key not configured. Please set it in Settings."

        try:
            params = {
                "q": city.strip(),
                "appid": self.api_key,
                "units": "metric",
            }
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            raw = response.json()
            return self._parse(raw), None

        except requests.exceptions.HTTPError:
            status = response.status_code
            if status == 404:
                msg = f"City '{city}' not found. Please check the spelling."
            elif status == 401:
                msg = "Invalid API key. Please verify your key in Settings."
            elif status == 429:
                msg = "API rate limit reached. Please wait and try again."
            else:
                msg = f"HTTP Error {status}: {response.text[:120]}"
            return None, msg

        except requests.exceptions.ConnectionError:
            return None, "No internet connection. Please check your network."

        except requests.exceptions.Timeout:
            return None, "Request timed out. Please try again."

        except requests.exceptions.RequestException as exc:
            return None, f"API request failed: {exc}"

        except (json.JSONDecodeError, KeyError):
            return None, "Failed to parse the API response."

    def _parse(self, data: dict) -> dict:
        """Convert raw API JSON into a clean, flat dictionary."""
        weather = {
            "city": data["name"],
            "country": data["sys"]["country"],
            "temperature": round(data["main"]["temp"], 1),
            "feels_like": round(data["main"]["feels_like"], 1),
            "temp_min": round(data["main"]["temp_min"], 1),
            "temp_max": round(data["main"]["temp_max"], 1),
            "humidity": data["main"]["humidity"],
            "pressure": data["main"]["pressure"],
            "condition": data["weather"][0]["main"],
            "description": data["weather"][0]["description"].title(),
            "icon_code": data["weather"][0]["icon"],
            "wind_speed": round(data["wind"]["speed"], 1),
            "wind_deg": data["wind"].get("deg", 0),
            "clouds": data["clouds"]["all"],
            "visibility": data.get("visibility", 0),
            "rain_1h": data.get("rain", {}).get("1h", 0),
            "rain_3h": data.get("rain", {}).get("3h", 0),
            "snow_1h": data.get("snow", {}).get("1h", 0),
            "sunrise": datetime.fromtimestamp(data["sys"]["sunrise"]).strftime("%H:%M"),
            "sunset": datetime.fromtimestamp(data["sys"]["sunset"]).strftime("%H:%M"),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        return weather

    @staticmethod
    def get_alerts(weather_data: dict) -> list:
        """Analyse weather data and return a list of alert tuples: [(text, colour_key), ...]"""
        alerts = []
        cond = weather_data.get("condition", "").lower()
        wind = weather_data.get("wind_speed", 0)
        rain = weather_data.get("rain_1h", 0)
        snow = weather_data.get("snow_1h", 0)
        temp = weather_data.get("temperature", 0)

        if cond == "thunderstorm":
            alerts.append(("⚡ Thunderstorm Warning", "red"))
        if cond == "tornado":
            alerts.append(("🌪️ Tornado Warning", "red"))
        if wind > 15:
            alerts.append(("💨 High Wind Alert", "orange"))
        if rain > 5:
            alerts.append(("🌧️ Heavy Rain Warning", "orange"))
        if snow > 2:
            alerts.append(("❄️ Heavy Snow Alert", "orange"))
        if temp > 40:
            alerts.append(("🔥 Extreme Heat Warning", "red"))
        elif temp > 35:
            alerts.append(("🥵 Heat Advisory", "orange"))
        if temp < -10:
            alerts.append(("🥶 Extreme Cold Warning", "red"))
        elif temp < 0:
            alerts.append(("❄️ Freeze Warning", "orange"))
        if cond in ("rain", "drizzle"):
            alerts.append(("☔ Rain Alert — Carry an umbrella!", "blue"))

        return alerts


# ══════════════════════════════════════════════
# MODULE 2: Data Storage
# ══════════════════════════════════════════════
class DataStorage:
    """Manages weather history with JSON auto-save and CSV export."""

    def __init__(self, json_path: str = "weather_history.json",
                 csv_path: str = "weather_history.csv",
                 max_records: int = 10000):
        self.json_path = json_path
        self.csv_path = csv_path
        self.max_records = max_records
        self.records: list = self._load_json()

    def _load_json(self) -> list:
        if os.path.exists(self.json_path):
            try:
                with open(self.json_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
            except (json.JSONDecodeError, IOError):
                return []
        return []

    def _save_json(self) -> None:
        try:
            with open(self.json_path, "w", encoding="utf-8") as fh:
                json.dump(self.records, fh, indent=2, ensure_ascii=False)
        except IOError as exc:
            print(f"[DataStorage] JSON write error: {exc}")

    def add_record(self, weather_data: dict) -> None:
        record = {
            "city": weather_data["city"],
            "country": weather_data["country"],
            "temperature": weather_data["temperature"],
            "feels_like": weather_data["feels_like"],
            "temp_min": weather_data["temp_min"],
            "temp_max": weather_data["temp_max"],
            "humidity": weather_data["humidity"],
            "pressure": weather_data["pressure"],
            "condition": weather_data["condition"],
            "description": weather_data["description"],
            "wind_speed": weather_data["wind_speed"],
            "wind_deg": weather_data["wind_deg"],
            "clouds": weather_data["clouds"],
            "visibility": weather_data["visibility"],
            "rain_1h": weather_data["rain_1h"],
            "snow_1h": weather_data["snow_1h"],
            "timestamp": weather_data["timestamp"],
            "date": weather_data["date"],
            "time": weather_data["time"],
        }
        self.records.append(record)
        if len(self.records) > self.max_records:
            self.records = self.records[-self.max_records:]
        self._save_json()

    def get_all_records(self) -> list:
        return list(self.records)

    def get_unique_cities(self) -> list:
        return sorted({r["city"] for r in self.records})

    def get_unique_dates(self) -> list:
        return sorted({r["date"] for r in self.records})

    def filter_by_city(self, city: str) -> list:
        lc = city.lower()
        return [r for r in self.records if r["city"].lower() == lc]

    def filter_by_date(self, date_str: str) -> list:
        return [r for r in self.records if r["date"] == date_str]

    def filter_by_date_range(self, start: str, end: str) -> list:
        try:
            d_start = datetime.strptime(start, "%Y-%m-%d").date()
            d_end = datetime.strptime(end, "%Y-%m-%d").date()
        except ValueError:
            return []
        result = []
        for r in self.records:
            try:
                d_rec = datetime.strptime(r["date"], "%Y-%m-%d").date()
                if d_start <= d_rec <= d_end:
                    result.append(r)
            except ValueError:
                continue
        return result

    def export_csv(self, filepath: str = None) -> tuple:
        filepath = filepath or self.csv_path
        if not self.records:
            return False, "No records to export."
        try:
            fieldnames = list(self.records[0].keys())
            with open(filepath, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.records)
            return True, f"Exported {len(self.records)} records to {filepath}"
        except IOError as exc:
            return False, f"CSV export error: {exc}"

    def clear_all(self) -> None:
        self.records.clear()
        self._save_json()

    def record_count(self) -> int:
        return len(self.records)


# ══════════════════════════════════════════════
# MODULE 3: Dashboard GUI
# ══════════════════════════════════════════════
class WeatherDashboard:
    """Tkinter-based Weather Tracking Dashboard."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🌤️  Weather Tracking Dashboard")
        self.root.geometry("1220x820")
        self.root.minsize(1100, 700)
        self.root.configure(bg=COLORS["bg_dark"])

        # Core modules
        self.storage = DataStorage()
        self.api = None
        self.current_weather = None

        # State
        self.tracked_cities = []
        self.auto_refresh_on = False

        # Build UI
        self._apply_styles()
        self._build_sidebar()
        self._build_content_area()

        # Load saved API key
        self._load_saved_key()

        # Show welcome / API-key dialog shortly after launch
        self.root.after(400, self._maybe_show_key_dialog)

    # ──────────────────────────────────────────
    # Style setup
    # ──────────────────────────────────────────
    def _apply_styles(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure("Dark.Treeview",
                    background=COLORS["card"],
                    foreground=COLORS["text_pri"],
                    fieldbackground=COLORS["card"],
                    font=("Segoe UI", 9),
                    rowheight=26)
        s.configure("Dark.Treeview.Heading",
                    background=COLORS["bg_light"],
                    foreground=COLORS["text_pri"],
                    font=("Segoe UI", 9, "bold"))
        s.map("Dark.Treeview",
              background=[("selected", COLORS["accent"])])

    # ──────────────────────────────────────────
    # Sidebar
    # ──────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = tk.Frame(self.root, bg=COLORS["bg_medium"], width=230)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo
        frm = tk.Frame(self.sidebar, bg=COLORS["bg_medium"])
        frm.pack(fill="x", pady=(20, 5), padx=15)
        tk.Label(frm, text="🌤️", font=("Segoe UI Emoji", 30),
                 bg=COLORS["bg_medium"], fg=COLORS["text_pri"]).pack()
        tk.Label(frm, text="Weather Dashboard", font=("Segoe UI", 13, "bold"),
                 bg=COLORS["bg_medium"], fg=COLORS["text_pri"]).pack(pady=(5, 0))

        tk.Frame(self.sidebar, bg=COLORS["accent"], height=2).pack(fill="x", padx=20, pady=15)

        # Navigation buttons
        nav = tk.Frame(self.sidebar, bg=COLORS["bg_medium"])
        nav.pack(fill="x", padx=10)

        items = [
            ("🌡️   Get Weather",  self._page_get_weather),
            ("📋   View History",  self._page_view_history),
            ("📊   Analyze Data",  self._page_analyze),
            ("💾   Save / Export", self._page_save_export),
            ("⚙️   Settings",      self._page_settings),
        ]
        self.nav_btns = []
        for text, cmd in items:
            btn = tk.Button(nav, text=text, command=cmd,
                            font=("Segoe UI", 11), anchor="w",
                            bg=COLORS["bg_medium"], fg=COLORS["text_sec"],
                            activebackground=COLORS["bg_light"],
                            activeforeground=COLORS["text_pri"],
                            relief="flat", cursor="hand2", padx=15, pady=10, bd=0)
            btn.pack(fill="x", pady=2)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=COLORS["bg_light"], fg=COLORS["text_pri"]))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=COLORS["bg_medium"], fg=COLORS["text_sec"]))
            self.nav_btns.append(btn)

        # Spacer
        tk.Frame(self.sidebar, bg=COLORS["bg_medium"]).pack(fill="both", expand=True)

        # Auto-refresh checkbox
        self.auto_var = tk.BooleanVar(value=False)
        tk.Checkbutton(self.sidebar, text=" Auto-refresh (5 min)",
                       variable=self.auto_var, command=self._toggle_auto_refresh,
                       bg=COLORS["bg_medium"], fg=COLORS["text_sec"],
                       selectcolor=COLORS["bg_light"],
                       activebackground=COLORS["bg_medium"],
                       activeforeground=COLORS["text_pri"],
                       font=("Segoe UI", 9)).pack(anchor="w", padx=15, pady=(0, 5))

        # API status
        self.api_status_lbl = tk.Label(self.sidebar, text="🔑 API Key: Not Set",
                                       font=("Segoe UI", 8),
                                       bg=COLORS["bg_medium"], fg=COLORS["danger"])
        self.api_status_lbl.pack(side="bottom", pady=10, padx=15, anchor="w")

        # Exit
        tk.Button(self.sidebar, text="🚪  Exit", command=self.exit_app,
                  font=("Segoe UI", 11), anchor="w",
                  bg=COLORS["bg_medium"], fg=COLORS["danger"],
                  activebackground=COLORS["accent"],
                  activeforeground=COLORS["text_pri"],
                  relief="flat", cursor="hand2", padx=15, pady=10, bd=0
                  ).pack(side="bottom", fill="x", padx=10, pady=(5, 10))

    # ──────────────────────────────────────────
    # Content area
    # ──────────────────────────────────────────
    def _build_content_area(self):
        self.content = tk.Frame(self.root, bg=COLORS["bg_dark"])
        self.content.pack(side="right", fill="both", expand=True)
        self._page_get_weather()

    def _clear_content(self):
        for w in self.content.winfo_children():
            w.destroy()

    def _highlight_nav(self, idx: int):
        for i, btn in enumerate(self.nav_btns):
            if i == idx:
                btn.config(bg=COLORS["bg_light"], fg=COLORS["accent"])
            else:
                btn.config(bg=COLORS["bg_medium"], fg=COLORS["text_sec"])

    # ══════════════════════════════════════════
    # PAGE: Get Weather
    # ══════════════════════════════════════════
    def _page_get_weather(self):
        self._clear_content()
        self._highlight_nav(0)

        # Header
        hdr = tk.Frame(self.content, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=30, pady=(25, 10))
        tk.Label(hdr, text="🌡️ Get Weather", font=("Segoe UI", 22, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_pri"]).pack(side="left")

        # Search bar
        search = tk.Frame(self.content, bg=COLORS["bg_dark"])
        search.pack(fill="x", padx=30, pady=10)

        tk.Label(search, text="City:", font=("Segoe UI", 11),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="left", padx=(0, 8))

        self.city_entry = tk.Entry(search, font=("Segoe UI", 12), width=30,
                                   bg=COLORS["card"], fg=COLORS["text_pri"],
                                   insertbackground=COLORS["text_pri"],
                                   relief="flat", bd=5)
        self.city_entry.pack(side="left", padx=(0, 10))
        self.city_entry.bind("<Return>", lambda e: self._fetch_weather())

        self._make_btn(search, "🔍 Search", self._fetch_weather, COLORS["accent"]).pack(side="left", padx=(0, 8))
        self._make_btn(search, "🔄 Refresh", self._refresh_weather, COLORS["bg_light"]).pack(side="left", padx=(0, 8))
        self._make_btn(search, "📌 Track City", self._add_tracked_city, COLORS["info"]).pack(side="left")

        # Alert bar (populated after fetch)
        self.alert_bar = tk.Frame(self.content, bg=COLORS["bg_dark"])
        self.alert_bar.pack(fill="x", padx=30, pady=(0, 5))

        # Weather result area
        self.weather_area = tk.Frame(self.content, bg=COLORS["bg_dark"])
        self.weather_area.pack(fill="both", expand=True, padx=30, pady=5)

        # Tracked-cities strip at bottom
        self.tracked_strip = tk.Frame(self.content, bg=COLORS["bg_dark"])
        self.tracked_strip.pack(fill="x", padx=30, pady=(0, 15))
        self._render_tracked_strip()

        self._show_placeholder()

    def _show_placeholder(self):
        self._clear_frame(self.weather_area)
        f = tk.Frame(self.weather_area, bg=COLORS["card"])
        f.pack(fill="both", expand=True, pady=5)
        tk.Label(f, text="🌍", font=("Segoe UI Emoji", 48),
                 bg=COLORS["card"], fg=COLORS["text_sec"]).pack(pady=(40, 10))
        tk.Label(f, text="Enter a city name to get weather information",
                 font=("Segoe UI", 14), bg=COLORS["card"],
                 fg=COLORS["text_sec"]).pack(pady=(0, 40))

    def _fetch_weather(self):
        city = self.city_entry.get().strip()
        if not city:
            messagebox.showwarning("Input Required", "Please enter a city name.")
            return
        if not self.api:
            messagebox.showerror("API Key Required",
                                 "Please set your API key in Settings first.")
            return
        self._show_loading()
        threading.Thread(target=self._fetch_thread, args=(city,), daemon=True).start()

    def _fetch_thread(self, city: str):
        data, err = self.api.fetch_weather(city)
        self.root.after(0, self._display_weather, data, err)

    def _show_loading(self):
        self._clear_frame(self.weather_area)
        f = tk.Frame(self.weather_area, bg=COLORS["card"])
        f.pack(fill="both", expand=True, pady=5)
        tk.Label(f, text="⏳ Fetching weather data…",
                 font=("Segoe UI", 14), bg=COLORS["card"],
                 fg=COLORS["text_sec"]).pack(expand=True)

    def _display_weather(self, data, err):
        self._clear_frame(self.weather_area)
        self._clear_frame(self.alert_bar)

        if err:
            f = tk.Frame(self.weather_area, bg=COLORS["card"])
            f.pack(fill="both", expand=True, pady=5)
            tk.Label(f, text="❌", font=("Segoe UI Emoji", 36),
                     bg=COLORS["card"], fg=COLORS["danger"]).pack(pady=(30, 10))
            tk.Label(f, text=err, font=("Segoe UI", 13),
                     bg=COLORS["card"], fg=COLORS["danger"]).pack(pady=(0, 30))
            return

        self.current_weather = data
        self.storage.add_record(data)

        # Alerts
        for text, sev in WeatherAPI.get_alerts(data):
            colour = {"red": COLORS["danger"], "orange": COLORS["warning"],
                      "blue": COLORS["info"]}.get(sev, COLORS["warning"])
            tk.Label(self.alert_bar, text=text, font=("Segoe UI", 10, "bold"),
                     bg=colour, fg="white", padx=10, pady=3).pack(side="left", padx=(0, 5))

        # ── Main card ──
        top = tk.Frame(self.weather_area, bg=COLORS["card"])
        top.pack(fill="x", pady=(0, 10))

        left = tk.Frame(top, bg=COLORS["card"])
        left.pack(side="left", fill="both", expand=True, padx=20, pady=15)
        tk.Label(left, text=f"{data['city']}, {data['country']}",
                 font=("Segoe UI", 20, "bold"),
                 bg=COLORS["card"], fg=COLORS["text_pri"]).pack(anchor="w")
        tk.Label(left, text=data["description"], font=("Segoe UI", 13),
                 bg=COLORS["card"], fg=COLORS["text_sec"]).pack(anchor="w", pady=(2, 10))
        tf = tk.Frame(left, bg=COLORS["card"])
        tf.pack(anchor="w")
        tk.Label(tf, text=f"{data['temperature']}°C", font=("Segoe UI", 42, "bold"),
                 bg=COLORS["card"], fg=COLORS["accent"]).pack(side="left")
        tk.Label(tf, text=f"  Feels like {data['feels_like']}°C",
                 font=("Segoe UI", 13), bg=COLORS["card"],
                 fg=COLORS["text_sec"]).pack(side="left", pady=(15, 0))

        right = tk.Frame(top, bg=COLORS["card"])
        right.pack(side="right", padx=20, pady=15)
        tk.Label(right, text=f"📅 {data['date']}", font=("Segoe UI", 10),
                 bg=COLORS["card"], fg=COLORS["text_sec"]).pack(anchor="e")
        tk.Label(right, text=f"🕐 {data['time']}", font=("Segoe UI", 10),
                 bg=COLORS["card"], fg=COLORS["text_sec"]).pack(anchor="e")

        # ── Detail grid ──
        grid = tk.Frame(self.weather_area, bg=COLORS["bg_dark"])
        grid.pack(fill="x")

        details = [
            ("💧 Humidity",    f"{data['humidity']}%"),
            ("💨 Wind Speed",  f"{data['wind_speed']} m/s"),
            ("🌡️ Min Temp",   f"{data['temp_min']}°C"),
            ("🌡️ Max Temp",   f"{data['temp_max']}°C"),
            ("🔽 Pressure",    f"{data['pressure']} hPa"),
            ("☁️ Clouds",      f"{data['clouds']}%"),
            ("👁️ Visibility", f"{data['visibility']/1000:.1f} km"),
            ("🌅 Sunrise",     data["sunrise"]),
            ("🌇 Sunset",      data["sunset"]),
            ("🌧️ Rain (1h)",  f"{data['rain_1h']} mm"),
            ("❄️ Snow (1h)",   f"{data['snow_1h']} mm"),
            ("🧭 Wind Dir",    f"{data['wind_deg']}°"),
        ]
        cols = 4
        for i, (label, value) in enumerate(details):
            c = tk.Frame(grid, bg=COLORS["card"], padx=12, pady=10)
            c.grid(row=i // cols, column=i % cols, padx=5, pady=5, sticky="nsew")
            grid.columnconfigure(i % cols, weight=1)
            tk.Label(c, text=label, font=("Segoe UI", 9),
                     bg=COLORS["card"], fg=COLORS["text_sec"]).pack(anchor="w")
            tk.Label(c, text=value, font=("Segoe UI", 14, "bold"),
                     bg=COLORS["card"], fg=COLORS["text_pri"]).pack(anchor="w", pady=(3, 0))

    def _refresh_weather(self):
        if self.current_weather:
            self.city_entry.delete(0, tk.END)
            self.city_entry.insert(0, self.current_weather["city"])
            self._fetch_weather()
        else:
            messagebox.showinfo("Info", "Search for a city first.")

    # ── Tracked cities ──
    def _add_tracked_city(self):
        if not self.current_weather:
            messagebox.showinfo("Info", "Fetch weather for a city first.")
            return
        city = self.current_weather["city"]
        if city not in self.tracked_cities:
            self.tracked_cities.append(city)
            self._render_tracked_strip()
            messagebox.showinfo("Tracked", f"📌 {city} added to tracked cities.")
        else:
            messagebox.showinfo("Info", f"{city} is already tracked.")

    def _render_tracked_strip(self):
        self._clear_frame(self.tracked_strip)
        if not self.tracked_cities:
            return
        tk.Label(self.tracked_strip, text="📌 Tracked:", font=("Segoe UI", 10, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="left", padx=(0, 8))
        for city in self.tracked_cities:
            self._make_btn(self.tracked_strip, f"📍 {city}",
                           lambda c=city: self._quick_fetch(c),
                           COLORS["bg_light"], size=9, px=8, py=3).pack(side="left", padx=3)
            tk.Button(self.tracked_strip, text="✕", font=("Segoe UI", 8),
                      bg=COLORS["danger"], fg="white", relief="flat", cursor="hand2",
                      padx=4, pady=2,
                      command=lambda c=city: self._remove_tracked(c)).pack(side="left", padx=(0, 5))

    def _quick_fetch(self, city: str):
        self.city_entry.delete(0, tk.END)
        self.city_entry.insert(0, city)
        self._fetch_weather()

    def _remove_tracked(self, city: str):
        if city in self.tracked_cities:
            self.tracked_cities.remove(city)
            self._render_tracked_strip()

    # ══════════════════════════════════════════
    # PAGE: View History
    # ══════════════════════════════════════════
    def _page_view_history(self):
        self._clear_content()
        self._highlight_nav(1)

        hdr = tk.Frame(self.content, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=30, pady=(25, 10))
        tk.Label(hdr, text="📋 Weather History", font=("Segoe UI", 22, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_pri"]).pack(side="left")

        # Filters
        ff = tk.Frame(self.content, bg=COLORS["bg_dark"])
        ff.pack(fill="x", padx=30, pady=10)

        tk.Label(ff, text="City:", font=("Segoe UI", 10),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="left", padx=(0, 5))
        self.hist_city_var = tk.StringVar(value="All")
        cb = ttk.Combobox(ff, textvariable=self.hist_city_var,
                          values=["All"] + self.storage.get_unique_cities(),
                          width=18, state="readonly")
        cb.pack(side="left", padx=(0, 12))

        tk.Label(ff, text="From:", font=("Segoe UI", 10),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="left", padx=(0, 5))
        self.hist_from = self._dark_entry(ff, 12)
        self.hist_from.insert(0, "YYYY-MM-DD")
        self.hist_from.pack(side="left", padx=(0, 8))

        tk.Label(ff, text="To:", font=("Segoe UI", 10),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="left", padx=(0, 5))
        self.hist_to = self._dark_entry(ff, 12)
        self.hist_to.insert(0, "YYYY-MM-DD")
        self.hist_to.pack(side="left", padx=(0, 10))

        self._make_btn(ff, "🔍 Apply", self._apply_hist_filter, COLORS["accent"]).pack(side="left", padx=(0, 5))
        self._make_btn(ff, "✕ Clear", self._clear_hist_filter, COLORS["bg_light"]).pack(side="left", padx=(0, 15))

        tk.Label(ff, text=f"Records: {self.storage.record_count()}", font=("Segoe UI", 10),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="right")

        # Treeview
        tf = tk.Frame(self.content, bg=COLORS["card"])
        tf.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        cols = ("timestamp", "city", "country", "temp", "feels", "condition", "humidity", "wind")
        self.hist_tree = ttk.Treeview(tf, columns=cols, show="headings", height=22,
                                      style="Dark.Treeview")
        headings = {"timestamp": ("Timestamp", 155), "city": ("City", 120),
                    "country": ("Country", 70), "temp": ("Temp °C", 85),
                    "feels": ("Feels °C", 85), "condition": ("Condition", 120),
                    "humidity": ("Humidity %", 95), "wind": ("Wind m/s", 85)}
        for c, (h, w) in headings.items():
            self.hist_tree.heading(c, text=h)
            self.hist_tree.column(c, width=w, anchor="center")

        vsb = ttk.Scrollbar(tf, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=vsb.set)
        self.hist_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self._populate_tree(self.storage.get_all_records())

    def _populate_tree(self, records: list):
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        for r in reversed(records):
            self.hist_tree.insert("", "end", values=(
                r["timestamp"], r["city"], r["country"],
                r["temperature"], r["feels_like"], r["condition"],
                r["humidity"], r["wind_speed"]))

    def _apply_hist_filter(self):
        recs = self.storage.get_all_records()
        city = self.hist_city_var.get()
        if city != "All":
            recs = [r for r in recs if r["city"].lower() == city.lower()]
        fr = self.hist_from.get().strip()
        to = self.hist_to.get().strip()
        if fr and fr != "YYYY-MM-DD" and to and to != "YYYY-MM-DD":
            recs = self.storage.filter_by_date_range(fr, to)
            if city != "All":
                recs = [r for r in recs if r["city"].lower() == city.lower()]
        elif fr and fr != "YYYY-MM-DD":
            recs = [r for r in recs if r["date"] >= fr]
        elif to and to != "YYYY-MM-DD":
            recs = [r for r in recs if r["date"] <= to]
        self._populate_tree(recs)

    def _clear_hist_filter(self):
        self.hist_city_var.set("All")
        self.hist_from.delete(0, tk.END); self.hist_from.insert(0, "YYYY-MM-DD")
        self.hist_to.delete(0, tk.END);   self.hist_to.insert(0, "YYYY-MM-DD")
        self._populate_tree(self.storage.get_all_records())

    # ══════════════════════════════════════════
    # PAGE: Analyze Data
    # ══════════════════════════════════════════
    def _page_analyze(self):
        self._clear_content()
        self._highlight_nav(2)

        hdr = tk.Frame(self.content, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=30, pady=(25, 10))
        tk.Label(hdr, text="📊 Weather Analysis", font=("Segoe UI", 22, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_pri"]).pack(side="left")

        records = self.storage.get_all_records()
        if not records:
            f = tk.Frame(self.content, bg=COLORS["card"])
            f.pack(fill="both", expand=True, padx=30, pady=10)
            tk.Label(f, text="📊", font=("Segoe UI Emoji", 48),
                     bg=COLORS["card"], fg=COLORS["text_sec"]).pack(pady=(40, 10))
            tk.Label(f, text="No data yet. Fetch some weather first!",
                     font=("Segoe UI", 14), bg=COLORS["card"],
                     fg=COLORS["text_sec"]).pack(pady=(0, 40))
            return

        # Controls
        ctrl = tk.Frame(self.content, bg=COLORS["bg_dark"])
        ctrl.pack(fill="x", padx=30, pady=10)

        tk.Label(ctrl, text="City:", font=("Segoe UI", 10),
                 bg=COLORS["bg_dark"], fg=COLORS["text_sec"]).pack(side="left", padx=(0, 5))
        self.ana_city_var = tk.StringVar()
        cities = self.storage.get_unique_cities()
        cb = ttk.Combobox(ctrl, textvariable=self.ana_city_var,
                          values=cities, width=20, state="readonly")
        if cities:
            cb.set(cities[0])
        cb.pack(side="left", padx=(0, 15))

        for txt, cmd in [("📈 Temp Trend", self._chart_temp),
                         ("💧 Humidity", self._chart_humidity),
                         ("💨 Wind", self._chart_wind),
                         ("📊 Compare", self._chart_compare),
                         ("📋 Summary", self._chart_summary)]:
            self._make_btn(ctrl, txt, cmd, COLORS["bg_light"], size=9, px=12, py=4).pack(side="left", padx=3)

        # Chart area
        self.chart_area = tk.Frame(self.content, bg=COLORS["card"])
        self.chart_area.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        self._chart_temp()

    def _analysis_data(self) -> list:
        city = self.ana_city_var.get()
        return self.storage.filter_by_city(city) if city else self.storage.get_all_records()

    def _chart_temp(self):
        data = self._analysis_data()
        if not data:
            return
        self._clear_frame(self.chart_area)
        fig = Figure(figsize=(10, 5), dpi=100, facecolor=COLORS["card"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(COLORS["card"])

        ts = [r["timestamp"] for r in data]
        temps = [r["temperature"] for r in data]
        feels = [r["feels_like"] for r in data]
        x = range(len(ts))

        ax.plot(x, temps, color=COLORS["accent"], lw=2, label="Temperature", marker="o", ms=4)
        ax.plot(x, feels, color=COLORS["info"], lw=1.5, ls="--", label="Feels Like", marker="s", ms=3)
        ax.set_ylabel("Temperature (°C)", color="white", fontsize=10)
        ax.set_title("Temperature Trend", color="white", fontsize=13, fontweight="bold")
        self._style_ax(ax, ts)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, self.chart_area)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _chart_humidity(self):
        data = self._analysis_data()
        if not data:
            return
        self._clear_frame(self.chart_area)
        fig = Figure(figsize=(10, 5), dpi=100, facecolor=COLORS["card"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(COLORS["card"])

        ts = [r["timestamp"] for r in data]
        hum = [r["humidity"] for r in data]
        x = range(len(ts))
        ax.fill_between(x, hum, alpha=0.3, color=COLORS["success"])
        ax.plot(x, hum, color=COLORS["success"], lw=2, label="Humidity", marker="o", ms=4)
        ax.set_ylabel("Humidity (%)", color="white", fontsize=10)
        ax.set_title("Humidity Trend", color="white", fontsize=13, fontweight="bold")
        ax.set_ylim(0, 100)
        self._style_ax(ax, ts)

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, self.chart_area)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _chart_wind(self):
        data = self._analysis_data()
        if not data:
            return
        self._clear_frame(self.chart_area)
        fig = Figure(figsize=(10, 5), dpi=100, facecolor=COLORS["card"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(COLORS["card"])

        ts = [r["timestamp"] for r in data]
        wind = [r["wind_speed"] for r in data]
        x = range(len(ts))
        ax.bar(x, wind, color=COLORS["warning"], alpha=0.7, label="Wind Speed")
        ax.set_ylabel("Wind Speed (m/s)", color="white", fontsize=10)
        ax.set_title("Wind Speed Trend", color="white", fontsize=13, fontweight="bold")
        self._style_ax(ax, ts, grid_axis="y")

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, self.chart_area)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _chart_compare(self):
        records = self.storage.get_all_records()
        if not records:
            return
        self._clear_frame(self.chart_area)
        city_temps = defaultdict(list)
        for r in records:
            city_temps[r["city"]].append(r["temperature"])

        cities = list(city_temps.keys())
        avgs = [sum(city_temps[c]) / len(city_temps[c]) for c in cities]
        mins = [min(city_temps[c]) for c in cities]
        maxs = [max(city_temps[c]) for c in cities]

        fig = Figure(figsize=(10, 5), dpi=100, facecolor=COLORS["card"])
        ax = fig.add_subplot(111)
        ax.set_facecolor(COLORS["card"])

        x = range(len(cities))
        w = 0.25
        ax.bar([i - w for i in x], mins, w, label="Min", color=COLORS["info"], alpha=0.8)
        ax.bar(x, avgs, w, label="Avg", color=COLORS["accent"], alpha=0.8)
        ax.bar([i + w for i in x], maxs, w, label="Max", color=COLORS["warning"], alpha=0.8)
        ax.set_xticks(list(x))
        ax.set_xticklabels(cities, rotation=45, ha="right")
        ax.set_ylabel("Temperature (°C)", color="white", fontsize=10)
        ax.set_title("City Temperature Comparison", color="white", fontsize=13, fontweight="bold")
        self._style_ax(ax, grid_axis="y")

        fig.tight_layout()
        canvas = FigureCanvasTkAgg(fig, self.chart_area)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _chart_summary(self):
        data = self._analysis_data()
        if not data:
            return
        self._clear_frame(self.chart_area)

        city_name = self.ana_city_var.get() or "All Cities"
        temps = [r["temperature"] for r in data]
        hum = [r["humidity"] for r in data]
        wind = [r["wind_speed"] for r in data]
        conds = defaultdict(int)
        for r in data:
            conds[r["condition"]] += 1
        top_cond = max(conds, key=conds.get) if conds else "N/A"

        sf = tk.Frame(self.chart_area, bg=COLORS["card"])
        sf.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(sf, text=f"📋 Summary — {city_name}",
                 font=("Segoe UI", 16, "bold"),
                 bg=COLORS["card"], fg=COLORS["accent"]).pack(anchor="w", pady=(0, 20))

        stats = [
            ("📊 Total Records", str(len(data))),
            ("🌡️ Avg Temp", f"{sum(temps)/len(temps):.1f}°C"),
            ("🔽 Min Temp", f"{min(temps):.1f}°C"),
            ("🔼 Max Temp", f"{max(temps):.1f}°C"),
            ("📏 Temp Range", f"{max(temps)-min(temps):.1f}°C"),
            ("💧 Avg Humidity", f"{sum(hum)/len(hum):.1f}%"),
            ("💨 Avg Wind", f"{sum(wind)/len(wind):.1f} m/s"),
            ("💨 Max Wind", f"{max(wind):.1f} m/s"),
            ("🌤️ Top Condition", top_cond),
        ]
        cols = 3
        for i, (lbl, val) in enumerate(stats):
            c = tk.Frame(sf, bg=COLORS["bg_medium"], padx=15, pady=12)
            c.grid(row=i // cols, column=i % cols, padx=8, pady=8, sticky="nsew")
            sf.columnconfigure(i % cols, weight=1)
            tk.Label(c, text=lbl, font=("Segoe UI", 9),
                     bg=COLORS["bg_medium"], fg=COLORS["text_sec"]).pack(anchor="w")
            tk.Label(c, text=val, font=("Segoe UI", 16, "bold"),
                     bg=COLORS["bg_medium"], fg=COLORS["text_pri"]).pack(anchor="w", pady=(3, 0))

    def _style_ax(self, ax, ts=None, grid_axis="both"):
        ax.tick_params(colors="white", labelsize=8)
        ax.legend(facecolor=COLORS["bg_medium"], edgecolor=COLORS["bg_light"],
                  labelcolor="white")
        ax.grid(True, alpha=0.2, color="white", axis=grid_axis)
        if ts:
            step = max(1, len(ts) // 10)
            x = range(len(ts))
            pos = list(x)[::step]
            lbls = [ts[i].split(" ")[0] for i in pos]
            ax.set_xticks(pos)
            ax.set_xticklabels(lbls, rotation=45, ha="right")
            ax.set_xlabel("Date", color="white", fontsize=10)

    # ══════════════════════════════════════════
    # PAGE: Save / Export
    # ══════════════════════════════════════════
    def _page_save_export(self):
        self._clear_content()
        self._highlight_nav(3)

        hdr = tk.Frame(self.content, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=30, pady=(25, 10))
        tk.Label(hdr, text="💾 Save & Export", font=("Segoe UI", 22, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_pri"]).pack(side="left")

        n = self.storage.record_count()
        wrap = tk.Frame(self.content, bg=COLORS["bg_dark"])
        wrap.pack(fill="both", expand=True, padx=30, pady=10)

        # CSV card
        c1 = self._card(wrap); c1.pack(fill="x", pady=5)
        tk.Label(c1, text="📄 Export to CSV", font=("Segoe UI", 16, "bold"),
                 bg=COLORS["card"], fg=COLORS["accent"]).pack(anchor="w")
        tk.Label(c1, text=f"Export all {n} records to a CSV spreadsheet file.",
                 font=("Segoe UI", 10), bg=COLORS["card"],
                 fg=COLORS["text_sec"]).pack(anchor="w", pady=(5, 15))
        self._make_btn(c1, "💾 Export CSV", self._do_export_csv, COLORS["accent"]).pack(anchor="w")

        # JSON info card
        c2 = self._card(wrap); c2.pack(fill="x", pady=5)
        jpath = os.path.abspath("weather_history.json")
        tk.Label(c2, text="📋 JSON Auto-Save", font=("Segoe UI", 16, "bold"),
                 bg=COLORS["card"], fg=COLORS["accent"]).pack(anchor="w")
        tk.Label(c2, text=f"Records are automatically saved to:\n{jpath}",
                 font=("Segoe UI", 10), bg=COLORS["card"],
                 fg=COLORS["text_sec"]).pack(anchor="w", pady=(5, 10))
        tk.Label(c2, text=f"Stored records: {n}", font=("Segoe UI", 12, "bold"),
                 bg=COLORS["card"], fg=COLORS["success"]).pack(anchor="w", pady=(0, 10))

        # Clear card
        c3 = self._card(wrap); c3.pack(fill="x", pady=5)
        tk.Label(c3, text="🗑️ Clear History", font=("Segoe UI", 16, "bold"),
                 bg=COLORS["card"], fg=COLORS["danger"]).pack(anchor="w")
        tk.Label(c3, text="Permanently delete all stored weather records.",
                 font=("Segoe UI", 10), bg=COLORS["card"],
                 fg=COLORS["text_sec"]).pack(anchor="w", pady=(5, 15))
        self._make_btn(c3, "🗑️ Clear All", self._do_clear_history, COLORS["danger"]).pack(anchor="w")

    def _do_export_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv"), ("All", "*.*")],
                                            title="Export Weather History")
        if path:
            ok, msg = self.storage.export_csv(path)
            (messagebox.showinfo if ok else messagebox.showerror)("Export", msg)

    def _do_clear_history(self):
        if messagebox.askyesno("Confirm", "Delete ALL weather history?\nThis cannot be undone!"):
            self.storage.clear_all()
            messagebox.showinfo("Done", "All records deleted.")

    # ══════════════════════════════════════════
    # PAGE: Settings
    # ══════════════════════════════════════════
    def _page_settings(self):
        self._clear_content()
        self._highlight_nav(4)

        hdr = tk.Frame(self.content, bg=COLORS["bg_dark"])
        hdr.pack(fill="x", padx=30, pady=(25, 10))
        tk.Label(hdr, text="⚙️ Settings", font=("Segoe UI", 22, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_pri"]).pack(side="left")

        wrap = tk.Frame(self.content, bg=COLORS["bg_dark"])
        wrap.pack(fill="both", expand=True, padx=30, pady=10)

        c1 = self._card(wrap); c1.pack(fill="x", pady=5)
        tk.Label(c1, text="🔑 OpenWeatherMap API Key",
                 font=("Segoe UI", 16, "bold"),
                 bg=COLORS["card"], fg=COLORS["accent"]).pack(anchor="w")
        tk.Label(c1, text="Get your free key: https://openweathermap.org/api",
                 font=("Segoe UI", 10), bg=COLORS["card"],
                 fg=COLORS["info"]).pack(anchor="w", pady=(5, 15))

        kf = tk.Frame(c1, bg=COLORS["card"])
        kf.pack(fill="x", pady=(0, 10))
        self.key_entry = tk.Entry(kf, font=("Segoe UI", 12), width=50,
                                  bg=COLORS["bg_medium"], fg=COLORS["text_pri"],
                                  insertbackground=COLORS["text_pri"],
                                  relief="flat", bd=5, show="•")
        if self.api:
            self.key_entry.insert(0, "••••••••")
        self.key_entry.pack(side="left", padx=(0, 10))
        self._make_btn(kf, "💾 Save Key", self._save_key, COLORS["accent"]).pack(side="left")

        self.key_status = tk.Label(c1, text="", font=("Segoe UI", 11, "bold"),
                                   bg=COLORS["card"])
        self._update_key_status_label(self.key_status)
        self.key_status.pack(anchor="w", pady=(10, 0))

        # Instructions card
        c2 = self._card(wrap); c2.pack(fill="x", pady=5)
        tk.Label(c2, text="ℹ️ How to Use", font=("Segoe UI", 16, "bold"),
                 bg=COLORS["card"], fg=COLORS["accent"]).pack(anchor="w")
        for line in [
            "1. Sign up at OpenWeatherMap for a free API key",
            "2. Enter your API key above and click 'Save Key'",
            "3. Search for any city in the 'Get Weather' tab",
            "4. Weather data is automatically saved to history",
            "5. Use 'Analyze Data' to view trends and statistics",
            "6. Enable 'Auto-refresh' to update tracked cities every 5 min",
            "7. Pin cities with '📌 Track City' for quick access",
        ]:
            tk.Label(c2, text=line, font=("Segoe UI", 10),
                     bg=COLORS["card"], fg=COLORS["text_sec"]).pack(anchor="w", pady=1)

    def _save_key(self):
        key = self.key_entry.get().strip()
        if not key or key == "••••••••":
            messagebox.showwarning("Warning", "Please enter a valid API key.")
            return
        self.api = WeatherAPI(key)
        try:
            with open(CONFIG_PATH, "w") as fh:
                json.dump({"api_key": key}, fh)
        except IOError:
            pass
        self._update_key_status_label(self.key_status)
        self.api_status_lbl.config(text="🔑 API Key: Active", fg=COLORS["success"])
        messagebox.showinfo("Saved", "API key saved successfully!")

    def _update_key_status_label(self, lbl):
        if self.api:
            lbl.config(text="✅ API Key Active", fg=COLORS["success"])
        else:
            lbl.config(text="❌ API Key Not Set", fg=COLORS["danger"])

    # ══════════════════════════════════════════
    # Auto-refresh
    # ══════════════════════════════════════════
    def _toggle_auto_refresh(self):
        if self.auto_var.get():
            if not self.tracked_cities:
                messagebox.showinfo("Info", "Track at least one city first (📌 Track City).")
                self.auto_var.set(False)
                return
            if not self.api:
                messagebox.showerror("Error", "Set your API key first.")
                self.auto_var.set(False)
                return
            self.auto_refresh_on = True
            threading.Thread(target=self._auto_refresh_loop, daemon=True).start()
        else:
            self.auto_refresh_on = False

    def _auto_refresh_loop(self):
        while self.auto_refresh_on and self.tracked_cities:
            for city in list(self.tracked_cities):
                if not self.auto_refresh_on:
                    return
                data, _ = self.api.fetch_weather(city)
                if data:
                    self.storage.add_record(data)
                time.sleep(1)
            for _ in range(AUTO_REFRESH_SEC):
                if not self.auto_refresh_on:
                    return
                time.sleep(1)

    # ══════════════════════════════════════════
    # API-key persistence & startup dialog
    # ══════════════════════════════════════════
    def _load_saved_key(self):
        try:
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as fh:
                    key = json.load(fh).get("api_key", "")
                    if key:
                        self.api = WeatherAPI(key)
                        self.api_status_lbl.config(text="🔑 API Key: Active",
                                                   fg=COLORS["success"])
        except (IOError, json.JSONDecodeError):
            pass

    def _maybe_show_key_dialog(self):
        if self.api:
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("🔑 API Key Setup")
        dlg.geometry("460x290")
        dlg.configure(bg=COLORS["bg_dark"])
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.resizable(False, False)
        dlg.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 460) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 290) // 2
        dlg.geometry(f"+{x}+{y}")

        tk.Label(dlg, text="🌤️ Welcome to Weather Dashboard",
                 font=("Segoe UI", 16, "bold"),
                 bg=COLORS["bg_dark"], fg=COLORS["text_pri"]).pack(pady=(20, 5))
        tk.Label(dlg, text="Enter your OpenWeatherMap API key to get started",
                 font=("Segoe UI", 10), bg=COLORS["bg_dark"],
                 fg=COLORS["text_sec"]).pack(pady=(0, 15))

        ent = tk.Entry(dlg, font=("Segoe UI", 12), width=42,
                       bg=COLORS["card"], fg=COLORS["text_pri"],
                       insertbackground=COLORS["text_pri"],
                       relief="flat", bd=5, show="•")
        ent.pack(pady=5)
        ent.focus_set()

        tk.Label(dlg, text="Free key → openweathermap.org/api",
                 font=("Segoe UI", 9), bg=COLORS["bg_dark"],
                 fg=COLORS["info"]).pack(pady=(5, 15))

        bf = tk.Frame(dlg, bg=COLORS["bg_dark"])
        bf.pack(pady=5)

        def save():
            key = ent.get().strip()
            if key:
                self.api = WeatherAPI(key)
                try:
                    with open(CONFIG_PATH, "w") as fh:
                        json.dump({"api_key": key}, fh)
                except IOError:
                    pass
                self.api_status_lbl.config(text="🔑 API Key: Active", fg=COLORS["success"])
            dlg.destroy()

        self._make_btn(bf, "💾 Save & Continue", save, COLORS["accent"]).pack(side="left", padx=5)
        self._make_btn(bf, "Skip", dlg.destroy, COLORS["bg_light"]).pack(side="left", padx=5)
        ent.bind("<Return>", lambda e: save())

    # ══════════════════════════════════════════
    # Exit
    # ══════════════════════════════════════════
    def exit_app(self):
        self.auto_refresh_on = False
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.root.quit()
            self.root.destroy()

    # ══════════════════════════════════════════
    # Small UI helpers
    # ══════════════════════════════════════════
    @staticmethod
    def _clear_frame(frame):
        for w in frame.winfo_children():
            w.destroy()

    def _card(self, parent):
        return tk.Frame(parent, bg=COLORS["card"], padx=30, pady=25)

    def _dark_entry(self, parent, width=20):
        return tk.Entry(parent, font=("Segoe UI", 10), width=width,
                        bg=COLORS["card"], fg=COLORS["text_pri"],
                        insertbackground=COLORS["text_pri"],
                        relief="flat", bd=3)

    def _make_btn(self, parent, text, cmd, bg, size=11, bold=True, px=20, py=5):
        weight = "bold" if bold else "normal"
        return tk.Button(parent, text=text, command=cmd,
                         font=("Segoe UI", size, weight),
                         bg=bg, fg="white",
                         activebackground=COLORS["accent_hov"],
                         activeforeground="white",
                         relief="flat", cursor="hand2", padx=px, pady=py)


# ══════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════
def main():
    root = tk.Tk()

    # Attempt to set window icon (ignore if unavailable)
    try:
        root.iconbitmap("weather_icon.ico")
    except Exception:
        pass

    app = WeatherDashboard(root)

    # Graceful close on window-X
    root.protocol("WM_DELETE_WINDOW", app.exit_app)

    root.mainloop()


if __name__ == "__main__":
    main()
