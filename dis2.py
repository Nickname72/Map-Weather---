import sys
import os
import tempfile
import glob
import requests
from datetime import datetime
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QComboBox, QMessageBox, QInputDialog, QFileDialog
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
import folium
from geopy.geocoders import Nominatim

# ---------------- CONFIG ----------------
OPENWEATHERMAP_API_KEY = "1a61ee3445e9c64367cd8d49289388a1"
DEFAULT_LOCATION = (50.4501, 30.5234)
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
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&lang={lang}&appid={api_key}"
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
        self.setWindowTitle("Map + Weather App")
        self.resize(1150, 720)
        self.current_lat = DEFAULT_LOCATION[0]
        self.current_lon = DEFAULT_LOCATION[1]
        self.current_lang = "en"
        self.map_tempfile = os.path.join(tempfile.gettempdir(), "map_weather_app_map.html")

        # Background
        self.bg_label = QLabel(self)
        self.bg_label.setScaledContents(True)
        self.bg_label.lower()

        # Header label
        self.header_label = QLabel("Weather & Map Explorer")
        self.header_label.setStyleSheet("font-size:28px; font-weight:bold; color:white; margin-bottom:5px;")
        self.header_label.setAlignment(QtCore.Qt.AlignCenter)

        # Webview
        self.webview = QWebEngineView()

        # Search & controls
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search city or address")
        self.search_btn = QPushButton("Search")
        self.loc_btn = QPushButton("Use My Location")
        self.lang_selector = QComboBox()
        self.lang_selector.addItem("English", "en")
        self.lang_selector.addItem("Українська", "uk")

        # Weather display
        self.temp_label = QLabel("—°C")
        self.temp_label.setObjectName("temp_label")
        self.desc_label = QLabel("")
        self.desc_label.setObjectName("desc_label")
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)

        # Buttons
        self.refresh_btn = QPushButton("Refresh weather")
        self.open_browser_btn = QPushButton("Open map in browser")
        self.resize_map_btn = QPushButton("Resize Map")
        self.change_bg_btn = QPushButton("Change Background")

        # Layouts
        top_layout = QVBoxLayout()
        top_layout.addWidget(self.header_label)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_input, stretch=6)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.loc_btn)
        search_layout.addStretch()
        top_layout.addLayout(search_layout)
        top_layout.setSpacing(4)  # зменшили відстань між заголовком і search

        left_layout = QVBoxLayout()
        left_layout.addLayout(top_layout)
        left_layout.addWidget(self.webview)
        left_frame = QFrame()
        left_frame.setLayout(left_layout)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.addWidget(self.lang_selector)
        right_layout.addSpacing(6)
        right_layout.addWidget(QLabel("Current Weather"))
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

        # Style
        self.setStyleSheet("""
            QWidget { background: transparent; }
            QFrame#glass { background-color: rgba(8,12,16,0.6); border-radius: 14px; }
            QLineEdit { background: rgba(255,255,255,0.95); color:#111; border-radius:10px; padding:8px;}
            QLineEdit::placeholder { color:#666; }
            QPushButton { background: #1e90ff; color:white; border:none; padding:6px 10px; border-radius:8px; }
            QPushButton:hover { background: #1c86ee; }
            QLabel#temp_label { font-size:72px; font-weight:700; color:#fff; }
            QLabel#desc_label { font-size:22px; color:#e6e6e6; }
            QLabel { color:#d6d6d6; font-size:14px; }
        """)

        # Connections
        self.search_btn.clicked.connect(self.on_search)
        self.loc_btn.clicked.connect(self.on_use_my_location)
        self.refresh_btn.clicked.connect(self.on_refresh)
        self.open_browser_btn.clicked.connect(self.open_map_in_browser)
        self.lang_selector.currentIndexChanged.connect(self.on_lang_change)
        self.resize_map_btn.clicked.connect(self.on_resize_map)
        self.change_bg_btn.clicked.connect(self.on_change_bg)

        # Init
        self.update_map()
        self.update_weather_and_background()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bg_label.resize(self.size())
        max_height = self.height() - 120
        self.webview.setMaximumHeight(max_height)
        self.webview.setMinimumHeight(300)
        if hasattr(self, "_current_bg_path") and self._current_bg_path:
            pix = QtGui.QPixmap(self._current_bg_path)
            pix = pix.scaled(self.size(), QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
            self.bg_label.setPixmap(pix)

    # --- Map & Weather ---
    def update_map(self):
        m = build_folium_map(self.current_lat, self.current_lon)
        save_map_html(m, self.map_tempfile)
        self.webview.load(QtCore.QUrl.fromLocalFile(self.map_tempfile))

    def update_weather_and_background(self):
        try:
            data = fetch_weather(self.current_lat, self.current_lon, OPENWEATHERMAP_API_KEY, self.current_lang)
            summary, desc, temp = weather_summary_text(data, self.current_lang)
            self.info_label.setText(summary)
            self.temp_label.setText(f"{temp:.0f}°C" if temp is not None else "—°C")
            self.desc_label.setText(desc.capitalize() if desc else "")
            bg = choose_background_by_description(desc)
            if bg:
                self._current_bg_path = bg
                self.resizeEvent(None)
        except Exception as e:
            self.info_label.setText(f"Weather error: {e}")

    # --- Actions ---
    def on_search(self):
        query = self.search_input.text().strip()
        if not query: return
        res = geocode_address(query)
        if res:
            self.current_lat, self.current_lon, _ = res
            self.update_map()
            self.update_weather_and_background()
        else:
            QMessageBox.warning(self, "Not found", "Location not found.")

    def on_use_my_location(self):
        try:
            r = requests.get("http://ip-api.com/json/", timeout=6).json()
            if r.get("status")=="success":
                self.current_lat, self.current_lon = r.get("lat"), r.get("lon")
                self.update_map()
                self.update_weather_and_background()
        except:
            QMessageBox.warning(self,"Error","Cannot get location")

    def on_refresh(self):
        self.update_weather_and_background()

    def open_map_in_browser(self):
        if os.path.exists(self.map_tempfile):
            import webbrowser
            webbrowser.open(f"file://{self.map_tempfile}")

    def on_lang_change(self, idx):
        self.current_lang = self.lang_selector.currentData()
        self.update_weather_and_background()

    def on_resize_map(self):
        w, ok1 = QInputDialog.getInt(self,"Map Width","Width:", self.webview.width(), 400,1200,10)
        if not ok1: return
        h, ok2 = QInputDialog.getInt(self,"Map Height","Height:", self.webview.height(),300,800,10)
        if not ok2: return
        self.webview.setFixedSize(w,h)

    def on_change_bg(self):
        path,_ = QFileDialog.getOpenFileName(self,"Select Background", BACKGROUNDS_DIR,"Images (*.png *.jpg *.bmp *.webp)")
        if path:
            self._current_bg_path = path
            self.resizeEvent(None)

# ---------------- MAIN ----------------
def main():
    app = QApplication(sys.argv)
    window = MapWeatherApp()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
