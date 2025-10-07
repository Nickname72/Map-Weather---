"""
Map + Weather App (with language switch)
Run in VS Code: python start_code.py
"""

import sys
import os
import tempfile
import json
import webbrowser
from datetime import datetime

import requests
import folium
from geopy.geocoders import Nominatim

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QMessageBox,
    QFrame,
    QComboBox,
)

try:
    from PyQt5.QtWebEngineWidgets import QWebEngineView
except Exception:
    raise RuntimeError("PyQtWebEngine is required. Install it with: pip install PyQtWebEngine")

# -------------------- CONFIG --------------------
OPENWEATHERMAP_API_KEY = "1a61ee3445e9c64367cd8d49289388a1"  # <--- встав сюди свій ключ
DEFAULT_LOCATION = (50.4501, 30.5234)  # Kyiv
DEFAULT_ZOOM = 6

# -------------------- FUNCTIONS --------------------

def save_map_html(m: folium.Map, filename: str):
    m.save(filename)


def build_folium_map(lat: float, lon: float, zoom: int = 6, marker: bool = True):
    m = folium.Map(location=[lat, lon], zoom_start=zoom, control_scale=True)
    folium.TileLayer("OpenStreetMap", attr="© OpenStreetMap").add_to(m)
    folium.TileLayer("CartoDB positron", attr="© CartoDB").add_to(m)
    folium.LayerControl().add_to(m)
    if marker:
        folium.Marker([lat, lon], tooltip="Selected location").add_to(m)
    m.add_child(folium.LatLngPopup())
    return m


def geocode_address(address: str):
    geolocator = Nominatim(user_agent="py_map_weather_app")
    try:
        location = geolocator.geocode(address, exactly_one=True, timeout=10)
        if location:
            return (location.latitude, location.longitude, location.address)
    except Exception:
        return None
    return None


def ip_geolocation():
    try:
        r = requests.get("http://ip-api.com/json/", timeout=6)
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "success":
                return (data.get("lat"), data.get("lon"), data)
    except Exception:
        return None
    return None


def fetch_weather(lat: float, lon: float, api_key: str, lang: str = "en"):
    if not api_key or api_key == "YOUR_API_KEY_HERE":
        raise RuntimeError("⚠️ Set your OpenWeatherMap API key in the code.")
    url = (
        f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}"
        f"&units=metric&lang={lang}&appid={api_key}"
    )
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    return r.json()


def weather_summary_text(data: dict):
    w = data.get("weather", [{}])[0]
    main = data.get("main", {})
    wind = data.get("wind", {})
    name = data.get("name") or ""
    desc = w.get("description", "-")
    temp = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    pressure = main.get("pressure")
    wind_spd = wind.get("speed")

    lines = []
    lines.append(f"📍 Location: {name}")
    lines.append(f"🌤 Weather: {desc.capitalize()}")
    if temp is not None:
        lines.append(f"🌡 Temperature: {temp} °C (feels like {feels} °C)")
    if hum is not None:
        lines.append(f"💧 Humidity: {hum}%")
    if pressure is not None:
        lines.append(f"🔽 Pressure: {pressure} hPa")
    if wind_spd is not None:
        lines.append(f"💨 Wind speed: {wind_spd} m/s")
    timestamp = data.get("dt")
    if timestamp:
        lines.append("⏰ Updated: " + datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M UTC"))
    return "\n".join(lines)

# -------------------- GUI --------------------

class MapWeatherApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map + Weather — Python App")
        self.resize(1100, 700)

        main_layout = QHBoxLayout(self)
        self.webview = QWebEngineView()
        self.map_tempfile = os.path.join(tempfile.gettempdir(), "map_weather_app_map.html")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search city or address (e.g. 'Lviv, Ukraine')")
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self.on_search)

        self.loc_btn = QPushButton("Use my location")
        self.loc_btn.clicked.connect(self.on_use_current_location)

        top_controls = QHBoxLayout()
        top_controls.addWidget(self.search_input)
        top_controls.addWidget(self.search_btn)
        top_controls.addWidget(self.loc_btn)

        left_layout = QVBoxLayout()
        left_layout.addLayout(top_controls)
        left_layout.addWidget(self.webview)

        left_frame = QFrame()
        left_frame.setLayout(left_layout)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(8, 8, 8, 8)

        self.weather_label = QLabel("Weather info will appear here")
        self.weather_label.setWordWrap(True)
        self.weather_label.setMinimumWidth(320)

        self.lang_selector = QComboBox()
        self.lang_selector.addItems(["English", "Українська"])
        self.lang_selector.currentIndexChanged.connect(self.on_language_change)
        self.current_lang = "en"

        self.refresh_btn = QPushButton("Refresh weather")
        self.refresh_btn.clicked.connect(self.on_refresh_weather)

        self.open_in_browser_btn = QPushButton("Open map in browser")
        self.open_in_browser_btn.clicked.connect(self.open_map_in_browser)

        right_layout.addWidget(QLabel("🌐 Language / Мова"))
        right_layout.addWidget(self.lang_selector)
        right_layout.addSpacing(10)
        right_layout.addWidget(QLabel("Current weather"))
        right_layout.addWidget(self.weather_label)
        right_layout.addStretch()
        right_layout.addWidget(self.refresh_btn)
        right_layout.addWidget(self.open_in_browser_btn)

        right_frame = QFrame()
        right_frame.setLayout(right_layout)

        main_layout.addWidget(left_frame, stretch=3)
        main_layout.addWidget(right_frame, stretch=1)
        self.setLayout(main_layout)

        self.current_lat = DEFAULT_LOCATION[0]
        self.current_lon = DEFAULT_LOCATION[1]
        self.current_zoom = DEFAULT_ZOOM
        self.reload_map()

    def reload_map(self, marker=True):
        m = build_folium_map(self.current_lat, self.current_lon, zoom=self.current_zoom, marker=marker)
        save_map_html(m, self.map_tempfile)
        self.webview.load(QtCore.QUrl.fromLocalFile(self.map_tempfile))

    def on_search(self):
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.information(self, "Info", "Enter a search query.")
            return
        try:
            res = geocode_address(query)
            if not res:
                QMessageBox.warning(self, "Not found", "Location not found.")
                return
            lat, lon, address = res
            self.current_lat = lat
            self.current_lon = lon
            self.current_zoom = 10
            self.reload_map(marker=True)
            self.get_and_show_weather(lat, lon)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Search error: {e}")

    def on_use_current_location(self):
        try:
            res = ip_geolocation()
            if not res:
                QMessageBox.warning(self, "Error", "Could not determine location via IP.")
                return
            lat, lon, data = res
            self.current_lat = lat
            self.current_lon = lon
            self.current_zoom = 10
            self.reload_map(marker=True)
            self.get_and_show_weather(lat, lon)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Location error: {e}")

    def on_refresh_weather(self):
        try:
            self.get_and_show_weather(self.current_lat, self.current_lon)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Couldn't refresh weather: {e}")

    def on_language_change(self):
        text = self.lang_selector.currentText()
        self.current_lang = "uk" if text == "Українська" else "en"
        self.get_and_show_weather(self.current_lat, self.current_lon)

    def open_map_in_browser(self):
        if os.path.exists(self.map_tempfile):
            webbrowser.open(f"file://{self.map_tempfile}")
        else:
            QMessageBox.warning(self, "No map", "Map file not found.")

    def get_and_show_weather(self, lat, lon):
        try:
            data = fetch_weather(lat, lon, OPENWEATHERMAP_API_KEY, lang=self.current_lang)
            txt = weather_summary_text(data)
            self.weather_label.setText(txt)
        except Exception as e:
            self.weather_label.setText(f"Weather error: {e}")

# -------------------- MAIN --------------------
def main():
    app = QApplication(sys.argv)
    window = MapWeatherApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
