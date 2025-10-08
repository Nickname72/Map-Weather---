"""
Map + Weather — Modern UI with Resize and Change Background
Requirements:
  pip install requests folium geopy PyQt5 PyQtWebEngine
Place background images in ./backgrounds with names like:
  clear.jpg | clouds.jpg | rain.jpg | storm.jpg | snow.jpg
"""

import sys
import os
import glob
import tempfile
import requests
from datetime import datetime

from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import (
    QApplication, QLabel, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QWidget, QMessageBox, QFrame, QComboBox, QFileDialog, QInputDialog
)
from PyQt5.QtWebEngineWidgets import QWebEngineView

import folium
from geopy.geocoders import Nominatim

# ---------------- CONFIG ----------------
OPENWEATHERMAP_API_KEY = "1a61ee3445e9c64367cd8d49289388a1"  # Замінити своїм ключем
DEFAULT_LOCATION = (50.4501, 30.5234)  # Kyiv
DEFAULT_ZOOM = 6
SUPPORTED_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]

SCRIPT_DIR = os.path.dirname(__file__)
BACKGROUNDS_DIR = os.path.join(SCRIPT_DIR, "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

# ---------------- HELPERS ----------------
def find_background_for(key):
    pattern = os.path.join(BACKGROUNDS_DIR, f"{key}*.*")
    files = glob.glob(pattern)
    for f in files:
        if os.path.splitext(f)[1].lower() in SUPPORTED_EXTS:
            return f
    return None

BACKGROUND_IMAGES = {
    "clear": find_background_for("clear"),
    "clouds": find_background_for("clouds"),
    "rain": find_background_for("rain"),
    "storm": find_background_for("storm"),
    "snow": find_background_for("snow"),
}
BACKGROUND_IMAGES["default"] = BACKGROUND_IMAGES.get("clear") or None

def build_folium_map(lat, lon, zoom=DEFAULT_ZOOM, marker=True):
    m = folium.Map(location=[lat, lon], zoom_start=zoom, control_scale=True)
    folium.TileLayer("OpenStreetMap").add_to(m)
    folium.TileLayer("CartoDB positron").add_to(m)
    folium.LayerControl().add_to(m)
    if marker:
        folium.Marker([lat, lon], tooltip="Selected location").add_to(m)
    m.add_child(folium.LatLngPopup())
    return m

def save_map_html(m, filename):
    m.save(filename)

def geocode_address(address: str):
    geolocator = Nominatim(user_agent="py_map_weather_app")
    try:
        loc = geolocator.geocode(address, exactly_one=True, timeout=10)
        if loc:
            return (loc.latitude, loc.longitude, loc.address)
    except Exception:
        return None
    return None

def fetch_weather(lat: float, lon: float, api_key: str, lang: str = "en"):
    if not api_key:
        raise RuntimeError("OpenWeatherMap API key not set.")
    url = (
        f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}"
        f"&units=metric&lang={lang}&appid={api_key}"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

def choose_background_by_description(desc: str):
    w = (desc or "").lower()
    if "thunder" in w or "storm" in w:
        return BACKGROUND_IMAGES.get("storm") or BACKGROUND_IMAGES.get("rain") or BACKGROUND_IMAGES["default"]
    if "rain" in w or "drizzle" in w:
        return BACKGROUND_IMAGES.get("rain") or BACKGROUND_IMAGES["default"]
    if "snow" in w or "sleet" in w or "ice" in w:
        return BACKGROUND_IMAGES.get("snow") or BACKGROUND_IMAGES["default"]
    if "cloud" in w or "overcast" in w or "broken" in w or "scattered" in w:
        return BACKGROUND_IMAGES.get("clouds") or BACKGROUND_IMAGES["default"]
    if "clear" in w or "sun" in w:
        return BACKGROUND_IMAGES.get("clear") or BACKGROUND_IMAGES["default"]
    if "mist" in w or "fog" in w or "haze" in w:
        return BACKGROUND_IMAGES.get("clouds") or BACKGROUND_IMAGES["default"]
    return BACKGROUND_IMAGES["default"]

def weather_summary_text(data: dict, lang: str = "en"):
    w = data.get("weather", [{}])[0]
    main = data.get("main", {})
    wind = data.get("wind", {})
    name = data.get("name") or ""
    desc = w.get("description", "-").capitalize()
    temp = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    pressure = main.get("pressure")
    wind_spd = wind.get("speed")
    ts = data.get("dt")
    lines = []
    if lang == "uk":
        lines.append(f"📍 {name}")
        lines.append(f"🌤 {desc}")
        if temp is not None:
            lines.append(f"🌡 {temp:.1f} °C (відчувається як {feels:.1f} °C)")
        if hum is not None:
            lines.append(f"💧 Вологість: {hum}%")
        if pressure is not None:
            lines.append(f"🔽 Тиск: {pressure} hPa")
        if wind_spd is not None:
            lines.append(f"🍃 Вітер: {wind_spd:.1f} м/с")
        if ts:
            lines.append("⏰ Оновлено: " + datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC"))
    else:
        lines.append(f"📍 {name}")
        lines.append(f"🌤 {desc}")
        if temp is not None:
            lines.append(f"🌡 {temp:.1f} °C (feels like {feels:.1f} °C)")
        if hum is not None:
            lines.append(f"💧 Humidity: {hum}%")
        if pressure is not None:
            lines.append(f"🔽 Pressure: {pressure} hPa")
        if wind_spd is not None:
            lines.append(f"💨 Wind: {wind_spd:.1f} m/s")
        if ts:
            lines.append("⏰ Updated: " + datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC"))
    return "\n".join(lines), desc, temp

# ---------------- GUI ----------------
class MapWeatherApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map + Weather — Python App")
        self.resize(1150, 720)
        self.current_lat = DEFAULT_LOCATION[0]
        self.current_lon = DEFAULT_LOCATION[1]
        self.current_lang = "en"
        self.map_tempfile = os.path.join(tempfile.gettempdir(), "map_weather_app_map.html")

        # background
        self.bg_label = QLabel(self)
        self.bg_label.setScaledContents(True)
        self.bg_label.lower()

        # widgets
        self.webview = QWebEngineView()
        self.webview.setFixedHeight(480)  # стартовий менший розмір

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search city or address (e.g. 'Lviv, Ukraine')")
        self.search_btn = QPushButton("Search")
        self.loc_btn = QPushButton("Use my location")
        self.lang_selector = QComboBox()
        self.lang_selector.addItem("English", userData="en")
        self.lang_selector.addItem("Українська", userData="uk")

        self.temp_label = QLabel("—°C")
        self.temp_label.setObjectName("temp_label")
        self.desc_label = QLabel("")
        self.desc_label.setObjectName("desc_label")
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)

        self.refresh_btn = QPushButton("Refresh weather")
        self.open_browser_btn = QPushButton("Open map in browser")
        self.resize_map_btn = QPushButton("Resize Map")
        self.change_bg_btn = QPushButton("Change Background")

        # layout
        top_controls = QHBoxLayout()
        top_controls.addWidget(self.search_input, stretch=6)
        top_controls.addWidget(self.search_btn)
        top_controls.addWidget(self.loc_btn)
        top_controls.addStretch()

        left_layout = QVBoxLayout()
        left_layout.addLayout(top_controls)
        left_layout.addWidget(self.webview)
        left_frame = QFrame()
        left_frame.setLayout(left_layout)
        left_frame.setFrameShape(QFrame.NoFrame)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.addWidget(self.lang_selector)
        right_layout.addSpacing(6)
        right_layout.addWidget(QLabel("Current weather"))
        right_layout.addWidget(self.temp_label)
        right_layout.addWidget(self.desc_label)
        right_layout.addWidget(self.info_label)
        right_layout.addStretch()
        right_layout.addWidget(self.refresh_btn)
        right_layout.addWidget(self.open_browser_btn)
        right_layout.addWidget(self.resize_map_btn)
        right_layout.addWidget(self.change_bg_btn)

        right_frame = QFrame()
        right_frame.setObjectName("glass")
        right_frame.setLayout(right_layout)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(left_frame, stretch=3)
        main_layout.addWidget(right_frame, stretch=1)
        self.setLayout(main_layout)

        self.setStyleSheet("""
            QWidget { background: transparent; }
            QFrame#glass {
                background-color: rgba(8, 12, 16, 0.60);
                border-radius: 14px;
            }
            QLineEdit {
                background: rgba(255,255,255,0.95);
                color: #111111;
                border: 1px solid rgba(0,0,0,0.12);
                padding: 10px;
                border-radius: 10px;
            }
            QLineEdit::placeholder { color: #666666; }
            QPushButton {
                background: rgba(255,255,255,0.12);
                color: #eaeaea;
                border: none;
                padding: 8px 12px;
                border-radius: 8px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.18); }
            QLabel#temp_label { font-size: 72px; font-weight: 700; color: #ffffff; }
            QLabel#desc_label { font-size: 22px; color: #e6e6e6; }
            QLabel { color: #d6d6d6; font-size: 14px; }
        """)

        # connections
        self.search_btn.clicked.connect(self.on_search)
        self.loc_btn.clicked.connect(self.on_use_my_location)
        self.refresh_btn.clicked.connect(self.on_refresh)
        self.open_browser_btn.clicked.connect(self.open_map_in_browser)
        self.lang_selector.currentIndexChanged.connect(self.on_lang_change)
        self.resize_map_btn.clicked.connect(self.on_resize_map)
        self.change_bg_btn.clicked.connect(self.on_change_bg)

        self.update_map()
        self.update_weather_and_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bg_label.resize(self.size())
        if hasattr(self, "_current_bg_path") and self._current_bg_path:
            self._apply_background(self._current_bg_path)
        else:
            self._apply_gradient_background()

    # background
    def _apply_background(self, path):
        try:
            pix = QtGui.QPixmap(path)
            scaled = pix.scaled(self.size(), QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
            self.bg_label.setPixmap(scaled)
            self.bg_label.lower()
            self._current_bg_path = path
        except Exception:
            self._apply_gradient_background()
            self._current_bg_path = None

    def _apply_gradient_background(self):
        s = self.size()
        if s.width() <= 0 or s.height() <= 0: return
        pix = QtGui.QPixmap(s)
        painter = QtGui.QPainter(pix)
        grad = QtGui.QLinearGradient(0, 0, 0, s.height())
        grad.setColorAt(0.0, QtGui.QColor(24, 32, 36))
        grad.setColorAt(1.0, QtGui.QColor(12, 18, 22))
        painter.fillRect(pix.rect(), grad)
        painter.end()
        self.bg_label.setPixmap(pix)
        self.bg_label.lower()
        self._current_bg_path = None

    def set_background_by_path(self, path):
        if path and os.path.exists(path):
            self._apply_background(path)
        else:
            self._apply_gradient_background()

    # map & weather
    def update_map(self):
        m = build_folium_map(self.current_lat, self.current_lon, zoom=DEFAULT_ZOOM)
        save_map_html(m, self.map_tempfile)
        self.webview.load(QtCore.QUrl.fromLocalFile(self.map_tempfile))

    def update_weather_and_background(self):
        try:
            data = fetch_weather(self.current_lat, self.current_lon, OPENWEATHERMAP_API_KEY, lang=self.current_lang)
            summary, desc, temp = weather_summary_text(data, lang=self.current_lang)
            self.info_label.setText(summary)
            self.temp_label.setText(f"{temp:.0f}°C" if temp is not None else "—°C")
            self.desc_label.setText(desc.capitalize() if desc else "")
            bg = choose_background_by_description(desc)
            self.set_background_by_path(bg)
        except Exception as e:
            self.info_label.setText(f"Weather error: {e}")
            self.temp_label.setText("—°C")
            self.desc_label.setText("")
            self._apply_gradient_background()

    # UI actions
    def on_search(self):
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.information(self, "Info", "Enter a search query.")
            return
        res = geocode_address(query)
        if not res:
            QMessageBox.warning(self, "Not found", "Location not found.")
            return
        self.current_lat, self.current_lon, _ = res
        self.update_map()
        self.update_weather_and_background()

    def on_use_my_location(self):
        try:
            r = requests.get("http://ip-api.com/json/", timeout=6)
            if r.status_code == 200:
                d = r.json()
                if d.get("status") == "success":
                    self.current_lat = d.get("lat")
                    self.current_lon = d.get("lon")
                    self.update_map()
                    self.update_weather_and_background()
                    return
        except Exception:
            pass
        QMessageBox.warning(self, "Error", "Could not determine location via IP.")

    def on_refresh(self):
        self.update_weather_and_background()

    def open_map_in_browser(self):
        if os.path.exists(self.map_tempfile):
            import webbrowser
            webbrowser.open(f"file://{self.map_tempfile}")
        else:
            QMessageBox.warning(self, "No map", "Map file not found.")

    def on_lang_change(self, idx):
        code = self.lang_selector.currentData()
        self.current_lang = code or ("en" if idx == 0 else "uk")
        self.search_input.setPlaceholderText(
            "Пошук міста чи адреси (наприклад 'Львів, Україна')" if self.current_lang=="uk"
            else "Search city or address (e.g. 'Lviv, Ukraine')"
        )
        self.update_weather_and_background()

    # ---------------- Additional buttons ----------------
    def on_resize_map(self):
        w, ok1 = QInputDialog.getInt(self, "Map Width", "Enter map width:", self.webview.width(), 200, 2000, 10)
        if not ok1: return
        h, ok2 = QInputDialog.getInt(self, "Map Height", "Enter map height:", self.webview.height(), 200, 2000, 10)
        if not ok2: return
        self.webview.setFixedSize(w, h)

    def on_change_bg(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Background", BACKGROUNDS_DIR,
                                                   "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file_path:
            self.set_background_by_path(file_path)

# -------------------- MAIN --------------------
def main():
    app = QApplication(sys.argv)
    w = MapWeatherApp()
    w.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
