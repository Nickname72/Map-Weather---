import sys
import os
import tempfile
import glob
import requests
import webbrowser
import json
import time 
# import wikipedia # БІЛЬШЕ НЕ ПОТРІБНО: УСУВАЄМО ЗОВНІШНЮ ЗАЛЕЖНІСТЬ
from datetime import datetime
from PyQt5 import QtCore, QtGui
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLineEdit, QPushButton, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QComboBox, QMessageBox, QInputDialog, QFileDialog,
    QTextEdit, QScrollArea, QSizePolicy
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from geopy.geocoders import Nominatim
import folium

# ---------------- CONFIGURATION & CONSTANTS ----------------
OPENWEATHERMAP_API_KEY = "1a61ee3445e9c64367cd8d49289388a1" 
DEFAULT_LOCATION = (50.4501, 30.5234) # Київ, Україна
DEFAULT_ZOOM = 6
APP_USER_AGENT = "py_map_weather_app_v1.7_final_fallback"
GEOLOCATOR_TIMEOUT = 10
WEATHER_API_TIMEOUT = 10
IP_API_URL = "http://ip-api.com/json/"

# Налаштування файлів та директорій
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd()
BACKGROUNDS_DIR = os.path.join(SCRIPT_DIR, "backgrounds")
TEMP_DIR = tempfile.gettempdir()
MAP_TEMP_FILE = os.path.join(TEMP_DIR, "map_weather_app_map.html")
LOG_FILE = os.path.join(SCRIPT_DIR, "app_log.txt")

# Доступні розширення для фонових зображень
SUPPORTED_EXTS = [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif"]
os.makedirs(BACKGROUNDS_DIR, exist_ok=True) 

# Стилістичні константи
FONT_FAMILY = "Segoe UI, Arial, sans-serif"
COLOR_PRIMARY = "#1e90ff"
COLOR_HOVER = "#1c86ee"
COLOR_BACKGROUND = "rgba(8,12,16,0.6)"
COLOR_TEXT_LIGHT = "#d6d6d6"
COLOR_TEXT_WHITE = "#fff"

def log_message(msg):
    """Проста функція логування для відстеження подій у консолі та файлі."""
    timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    log_entry = f"{timestamp} {msg}"
    print(log_entry)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except Exception as e:
        print(f"ERROR: Не вдалося записати в лог-файл: {e}")

# ---------------- HELPERS: BACKGROUNDS ----------------
def find_background_for(key):
    """Шукає фонове зображення за ключем (clear, rain, snow тощо) у папці BACKGROUNDS_DIR."""
    log_message(f"INFO: Шукаю фон для ключа: {key}")
    for ext in SUPPORTED_EXTS:
        filename_pattern = os.path.join(BACKGROUNDS_DIR, f"{key}*{ext}")
        files = glob.glob(filename_pattern)
        if files:
            log_message(f"INFO: Знайдено фон: {files[0]} для ключа '{key}'")
            return files[0]
    log_message(f"WARNING: Фон для ключа '{key}' не знайдено в '{BACKGROUNDS_DIR}'.")
    return None

BACKGROUND_IMAGES = {
    "clear": find_background_for("clear"),
    "clouds": find_background_for("clouds"),
    "rain": find_background_for("rain"),
    "storm": find_background_for("storm"),
    "snow": find_background_for("snow"),
}
BACKGROUND_IMAGES["default"] = BACKGROUND_IMAGES.get("clear") or next((f for f in BACKGROUND_IMAGES.values() if f), None)
if not BACKGROUND_IMAGES["default"]:
    log_message(f"WARNING: Жодного фонового зображення за замовчуванням не знайдено у '{BACKGROUNDS_DIR}'.")


def choose_background_by_description(desc: str):
    """Вибирає фонове зображення відповідно до опису погоди."""
    w = (desc or "").lower()
    if "thunder" in w or "storm" in w:
        return BACKGROUND_IMAGES.get("storm") or BACKGROUND_IMAGES.get("rain") or BACKGROUND_IMAGES["default"]
    if "rain" in w or "drizzle" in w or "shower" in w:
        return BACKGROUND_IMAGES.get("rain") or BACKGROUND_IMAGES["default"]
    if "snow" in w or "sleet" in w or "ice" in w:
        return BACKGROUND_IMAGES.get("snow") or BACKGROUND_IMAGES["default"]
    if "cloud" in w or "overcast" in w or "broken" in w or "scattered" in w or "mist" in w or "fog" in w:
        return BACKGROUND_IMAGES.get("clouds") or BACKGROUND_IMAGES["default"]
    if "clear" in w or "sun" in w:
        return BACKGROUND_IMAGES.get("clear") or BACKGROUND_IMAGES["default"]
    return BACKGROUND_IMAGES["default"]

# ---------------- HELPERS: MAPS & GEOLOCATION ----------------
def build_folium_map(lat, lon, zoom=DEFAULT_ZOOM, marker=True):
    """Створює інтерактивну карту Folium з кількома шарами."""
    log_message(f"INFO: Створення карти для Lat: {lat}, Lon: {lon}")
    m = folium.Map(location=[lat, lon], zoom_start=zoom, control_scale=True)
    
    folium.TileLayer("OpenStreetMap", name="Standard").add_to(m)
    folium.TileLayer("CartoDB positron", name="Light").add_to(m)
    folium.TileLayer("CartoDB dark_matter", name="Dark").add_to(m)
    
    folium.LayerControl().add_to(m)
    if marker:
        folium.Marker([lat, lon], tooltip="Selected location", 
                      icon=folium.Icon(color='red', icon='info-sign')).add_to(m)
    m.add_child(folium.LatLngPopup())
    return m

def save_map_html(m, filename):
    """Зберігає карту Folium як HTML-файл у тимчасову директорію."""
    try:
        m.save(filename)
        log_message(f"INFO: Карта збережена у {filename}")
    except Exception as e:
        log_message(f"ERROR: Не вдалося зберегти карту у {filename}: {e}")

def geocode_address(address: str):
    """Геокодування адреси/місця за допомогою Nominatim (OpenStreetMap)."""
    geolocator = Nominatim(user_agent=APP_USER_AGENT)
    try:
        loc = geolocator.geocode(address, exactly_one=True, timeout=GEOLOCATOR_TIMEOUT)
        if loc:
            log_message(f"INFO: Геокодування успішне: {loc.address}")
            return (loc.latitude, loc.longitude, loc.address)
    except Exception as e:
        log_message(f"ERROR: Помилка геокодування '{address}': {e}")
        return None
    return None

# ---------------- HELPERS: WEATHER ----------------
def fetch_weather(lat: float, lon: float, api_key: str, lang: str = "en"):
    """Отримання поточної погоди від OpenWeatherMap."""
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&lang={lang}&appid={api_key}"
    log_message(f"INFO: Запит погоди для ({lat}, {lon})")
    try:
        r = requests.get(url, timeout=WEATHER_API_TIMEOUT)
        r.raise_for_status() 
        return r.json()
    except requests.exceptions.RequestException as e:
        log_message(f"ERROR: Помилка запиту погоди: {e}")
        if '401 Client Error' in str(e):
             raise ConnectionError("Помилка API: Невірний ключ OpenWeatherMap.") from e
        raise ConnectionError("Помилка підключення до служби погоди.") from e

def weather_summary_text(data: dict, lang: str = "en"):
    """Форматування даних погоди для відображення."""
    w = data.get("weather", [{}])[0]
    main = data.get("main", {})
    wind = data.get("wind", {})
    sys_data = data.get("sys", {})
    
    name = data.get("name") or data.get("timezone", "Невідоме місце")
    country = sys_data.get("country", "")
    full_name = f"{name}, {country}" if country else name
    
    desc = w.get("description", "—").capitalize()
    temp = main.get("temp")
    feels = main.get("feels_like")
    hum = main.get("humidity")
    pressure = main.get("pressure")
    wind_spd = wind.get("speed")
    ts = data.get("dt")
    
    lines = []
    
    if lang == "uk":
        lines.append(f"📍 {full_name}")
        lines.append(f"🌤 {desc}")
        if temp is not None and feels is not None:
            lines.append(f"🌡 {temp:.1f} °C (відчувається як {feels:.1f} °C)")
        if hum is not None:
            lines.append(f"💧 Вологість: {hum}%")
        if pressure is not None:
            lines.append(f"🔽 Тиск: {pressure} hPa")
        if wind_spd is not None:
            lines.append(f"🍃 Вітер: {wind_spd:.1f} м/с")
        if ts:
            lines.append("⏰ Оновлено: " + datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC"))
    else: # English (default)
        lines.append(f"📍 {full_name}")
        lines.append(f"🌤 {desc}")
        if temp is not None and feels is not None:
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

# ---------------- AI ASSISTANT IMPLEMENTATION: FALLBACK DB ----------------

# Внутрішня, надійна база знань
INTERNAL_KNOWLEDGE_DB = {
    # --- КРАЇНИ ---
    "грузія": ("**Країна:** Грузія (Сакартвело)\n**Столиця:** Тбілісі\n**Населення:** ~3.7 млн\n**Історія:** Країна з тисячолітньою історією, розташована на перехресті Європи та Азії. Відома виноробством та стародавніми храмами.", "country"),
    "georgia": ("**Country:** Georgia (Sakartvelo)\n**Capital:** Tbilisi\n**Population:** ~3.7 million\n**History:** A country with a thousand-year history, located at the crossroads of Europe and Asia. Known for its winemaking and ancient churches.", "country"),
    "україна": ("**Країна:** Україна\n**Столиця:** Київ\n**Населення:** ~41 млн (до 2022)\n**Особливості:** Друга за площею країна в Європі, відома своєю культурою та родючими чорноземами.", "country"),
    "казахстан": ("**Країна:** Казахстан\n**Столиця:** Астана\n**Населення:** ~20 млн\n**Особливості:** Дев'ята за площею країна світу. Відома космодромом Байконур та величезними степами.", "country"),
    "kazakhstan": ("**Country:** Kazakhstan\n**Capital:** Astana\n**Population:** ~20 million\n**Features:** Ninth largest country by area. Known for the Baikonur Cosmodrome and vast steppes.", "country"),
    "hungary": ("**Country:** Hungary\n**Capital:** Budapest\n**Population:** ~9.6 million\n**Features:** Known for its thermal waters, vibrant culture, and historical role in Central Europe.", "country"),
    
    # --- МІСТА ---
    "львів": ("**Місто:** Львів\n**Область:** Львівська\n**Історія:** Заснований у **13 столітті**. Головний культурний та освітній центр Західної України. Історичний центр Львова внесений до списку Світової спадщини ЮНЕСКО.", "city"),
    "винниця": ("**Місто:** Вінниця\n**Область:** Вінницька\n**Історія:** Перша згадка датується **1363 роком**. Назва, ймовірно, походить від слова 'віно'. Відома Європейським фонтаном Roshen.", "city"),
    "київ": ("**Місто:** Київ\n**Розташування:** Столиця України, на річці Дніпро.\n**Історія:** Одне з найдавніших міст Східної Європи, засноване у **V столітті**. Був центром Київської Русі.", "city"),
    "kyiv": ("**City:** Kyiv\n**Location:** Capital of Ukraine, situated on the Dnieper River.\n**History:** One of the oldest cities in Eastern Europe, founded in the **5th century**. It was the historical center of Kyivan Rus'.", "city"),
    "paris": ("**City:** Paris\n**Location:** Capital of France, on the River Seine.\n**History:** Known as 'The City of Love' and a global center for art and fashion since the **10th century**.", "city"),
    "париж": ("**Місто:** Париж\n**Розташування:** Столиця Франції, на річці Сена.\n**Історія:** Відомий як 'Місто кохання' та світовий центр мистецтва і моди. Тут знаходяться Ейфелева вежа та Лувр.", "city"),
}


class SearchWorker(QThread):
    """Потік для виконання пошуку інформації про місто/країну, використовуючи внутрішню базу."""
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, query: str, lang: str):
        super().__init__()
        self.query = query
        self.preferred_lang = lang

    def run(self):
        try:
            time.sleep(0.5) # Імітація "думки"
            
            q_lower = self.query.lower().strip()
            
            # 1. Спроба знайти у внутрішній базі
            if q_lower in INTERNAL_KNOWLEDGE_DB:
                summary, item_type = INTERNAL_KNOWLEDGE_DB[q_lower]
                
                # Форматування відповіді
                if item_type == "country":
                    header = f"<p style='color:#f1c40f; font-weight:bold;'>🌍 Країна-Асистент:</p>"
                else: # city
                    header = f"<p style='color:#76a9ff; font-weight:bold;'>🏙️ Місто-Асистент:</p>"
                    
                response_text = header + summary
                log_message(f"AI SUCCESS: Інформація про {self.query} отримана з внутрішньої бази.")
            else:
                # 2. Якщо не знайдено, використовуємо інтелектуальну заглушку
                log_message(f"AI WARNING: Запит '{self.query}' не знайдено у внутрішній базі. Генерую відповідь.")
                
                header = f"<p style='color:#e74c3c; font-weight:bold;'>Попередження (Не знайдено):</p>"
                
                # Спроба визначити, чи це країна або місто за геокодуванням (для більш інтелектуальної заглушки)
                geo_res = geocode_address(self.query)
                is_capital = "столицею" if geo_res and "capital" in geo_res[2].lower() else "місцем"
                
                response_text = (f"{header}Я не знайшов детальної інформації про **{self.query.title()}** у своїй поточній базі. "
                                 f"Проте, згідно з картографічними даними, це важливе {is_capital}. "
                                 f"Для цього місця потрібен постійний доступ до зовнішнього API.")

            self.result_ready.emit(response_text)
            
        except Exception as e:
            log_message(f"AI FATAL ERROR: Критична помилка у потоці пошуку: {e}")
            self.error_occurred.emit("Сталася критична помилка під час виконання запиту.")

class AICountryInfoDialog(QWidget):
    """Окреме діалогове вікно для AI-асистента з чатом."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Асистент: Внутрішня База Знань 🤖")
        self.resize(650, 550)
        self.worker = None
        self._setup_ui()
        self._setup_style()
        self.setWindowFlags(QtCore.Qt.Window)
        self.parent_app = parent

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        
        header = QLabel("🤖 AI-Консультант: Пошук у Внутрішній Базі")
        header.setStyleSheet(f"font-size:18px; font-weight:bold; color: #1abc9c; margin-bottom: 5px;")
        main_layout.addWidget(header)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setFont(QtGui.QFont(FONT_FAMILY, 10))
        self.chat_history.setHtml(
            "<p style='color:#f1c40f; font-weight:bold;'>AI-асистент:</p>"
            "Привіт! Я ваш асистент. Я використовую **внутрішню базу знань** для надійної демонстрації. Спробуйте ввести **Грузія, Львів, Вінниця, чи Hungary**."
        )
        main_layout.addWidget(self.chat_history)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Введіть назву країни або міста...")
        self.query_input.returnPressed.connect(self.send_query)
        
        self.send_btn = QPushButton("Надіслати запит")
        self.send_btn.clicked.connect(self.send_query)

        input_layout = QHBoxLayout()
        input_layout.addWidget(self.query_input, stretch=4)
        input_layout.addWidget(self.send_btn, stretch=1)
        main_layout.addLayout(input_layout)

    def _setup_style(self):
        self.setStyleSheet(f"""
            QWidget {{ 
                background-color: #2c3e50; 
                color: {COLOR_TEXT_WHITE};
                font-family: {FONT_FAMILY};
            }}
            QLineEdit {{ 
                background: rgba(255,255,255,0.95); 
                color:#111; 
                border-radius:10px; 
                padding:8px;
                border: 1px solid #bdc3c7;
            }}
            QPushButton {{ 
                background: #3498db; 
                color:white; 
                border:none; 
                padding:10px; 
                border-radius:8px; 
                font-weight: bold;
            }}
            QPushButton:hover {{ background: #2980b9; }}
            QTextEdit {{
                background-color: #34495e; 
                border: 2px solid #1abc9c; 
                border-radius: 10px;
                padding: 10px;
                color: {COLOR_TEXT_WHITE};
            }}
            QTextEdit p {{ margin-bottom: 5px; }}
        """)

    def send_query(self):
        query = self.query_input.text().strip()
        if not query or (self.worker and self.worker.isRunning()):
            return
        
        self.chat_history.append(f"<p style='color:#1abc9c; font-weight:bold;'>Ви:</p>{query}")
        self.query_input.clear()
        
        self.send_btn.setText("ШІ думає... ⏳")
        self.send_btn.setEnabled(False)
        
        current_lang = self.parent_app.current_lang if self.parent_app else "uk"
        
        self.worker = SearchWorker(query, current_lang)
        self.worker.result_ready.connect(self.handle_result)
        self.worker.error_occurred.connect(self.handle_error)
        self.worker.finished.connect(self.reset_ui)
        self.worker.start()

    def handle_result(self, result: str):
        html_result = result.replace('**', '<b>') 
        self.chat_history.append(f"<p style='color:#f1c40f; font-weight:bold;'>AI-асистент:</p>{html_result}")

    def handle_error(self, error: str):
        self.chat_history.append(f"<p style='color:#e74c3c; font-weight:bold;'>Помилка:</p>{error}")

    def reset_ui(self):
        self.send_btn.setText("Надіслати запит")
        self.send_btn.setEnabled(True)

# ---------------- GUI MAIN APPLICATION ----------------
class MapWeatherApp(QWidget):
    """Основний клас додатку для відображення карти та погоди."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Map & Weather Explorer Pro 🗺️🌦️")
        self.resize(1200, 750) 
        self.current_lat = DEFAULT_LOCATION[0]
        self.current_lon = DEFAULT_LOCATION[1]
        self.current_lang = "uk"
        self.map_tempfile = MAP_TEMP_FILE
        self._current_bg_path = BACKGROUND_IMAGES["default"]
        self.ai_assistant_dialog = None
        
        self._setup_ui()
        self._setup_style()
        self._setup_connections()
        
        self.update_map()
        self.update_weather_and_background()

    def _setup_ui(self):
        # Background
        self.bg_label = QLabel(self)
        self.bg_label.setScaledContents(True)
        self.bg_label.lower()

        # Header label
        self.header_label = QLabel("Weather & Map Explorer")
        self.header_label.setAlignment(QtCore.Qt.AlignCenter)

        # Webview (Map)
        self.webview = QWebEngineView()
        self.webview.setMinimumHeight(350)

        # Search & controls
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search city or address (e.g., London, Kyiv)")
        self.search_btn = QPushButton("Search 🔍")
        self.loc_btn = QPushButton("My Location 🏠")
        self.search_input.returnPressed.connect(self.on_search)
        
        self.lang_selector = QComboBox()
        self.lang_selector.addItem("English", "en")
        self.lang_selector.addItem("Українська", "uk")
        if self.current_lang == "uk":
            self.lang_selector.setCurrentIndex(1) 

        # Weather display
        self.temp_label = QLabel("—°C")
        self.temp_label.setObjectName("temp_label")
        self.desc_label = QLabel("")
        self.desc_label.setObjectName("desc_label")
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # Action Buttons
        self.refresh_btn = QPushButton("Refresh Weather 🔄")
        self.open_browser_btn = QPushButton("Open Map in Browser 🌐")
        self.resize_map_btn = QPushButton("Resize Map Window 📏")
        self.change_bg_btn = QPushButton("Change Background 🖼️")
        self.ai_assistant_btn = QPushButton("AI Асистент (DB) 🤖")
        self.ai_assistant_btn.setObjectName("ai_assistant_btn")

        # Layouts
        top_layout = QVBoxLayout()
        top_layout.addWidget(self.header_label)

        search_layout = QHBoxLayout()
        search_layout.addWidget(self.search_input, stretch=6)
        search_layout.addWidget(self.search_btn)
        search_layout.addWidget(self.loc_btn)
        top_layout.addLayout(search_layout)
        top_layout.setSpacing(6)

        left_layout = QVBoxLayout()
        left_layout.addLayout(top_layout)
        left_layout.addWidget(self.webview)
        left_frame = QFrame()
        left_frame.setLayout(left_layout)
        left_frame.setObjectName("left_panel")

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(15, 15, 15, 15)
        
        right_layout.addWidget(self.lang_selector)
        right_layout.addSpacing(10)
        
        right_layout.addWidget(QLabel("--- Current Weather Status ---"))
        right_layout.addWidget(self.temp_label)
        right_layout.addWidget(self.desc_label)
        right_layout.addWidget(self.info_label)
        right_layout.addStretch()
        
        right_layout.addWidget(self.ai_assistant_btn) 
        right_layout.addWidget(self.refresh_btn)
        right_layout.addWidget(self.open_browser_btn)
        right_layout.addWidget(self.resize_map_btn)
        right_layout.addWidget(self.change_bg_btn)

        right_frame = QFrame()
        right_frame.setObjectName("glass")
        right_frame.setLayout(right_layout)

        main_layout = QHBoxLayout(self)
        main_layout.addWidget(left_frame, stretch=4)
        main_layout.addWidget(right_frame, stretch=1)
        self.setLayout(main_layout)

    def _setup_style(self):
        self.setStyleSheet(f"""
            QWidget {{ background: transparent; font-family: {FONT_FAMILY}; }}
            
            QFrame#glass {{ 
                background-color: {COLOR_BACKGROUND}; 
                border-radius: 18px; 
            }}
            
            QFrame#left_panel {{ background: transparent; }}

            QLineEdit {{ 
                background: rgba(255,255,255,0.98); 
                color:#111; 
                border-radius:12px; 
                padding:10px 12px;
                border: 1px solid #ccc;
            }}
            QLineEdit::placeholder {{ color:#888; }}
            
            QComboBox {{
                background: rgba(255,255,255,0.9);
                border-radius: 8px;
                padding: 6px;
                color: #333;
            }}
            
            QPushButton {{ 
                background: {COLOR_PRIMARY}; 
                color:white; 
                border:none; 
                padding:10px 15px; 
                border-radius:10px; 
                font-weight: 600;
                margin-top: 5px;
            }}
            QPushButton:hover {{ background: {COLOR_HOVER}; }}
            
            QPushButton#ai_assistant_btn {{
                background: #e74c3c; 
                margin-bottom: 15px;
            }}
            QPushButton#ai_assistant_btn:hover {{ background: #c0392b; }}

            QLabel {{ color:{COLOR_TEXT_LIGHT}; font-size:16px; }}
            QLabel#temp_label {{ font-size:90px; font-weight:800; color:{COLOR_TEXT_WHITE}; margin-bottom: -15px; }}
            QLabel#desc_label {{ font-size:24px; color:#f1c40f; font-weight: 500; }}
            
            QLabel#header_label {{ 
                font-size:48px; 
                font-weight:bold; 
                color:#FFFFFF; 
                margin-bottom:10px;
                padding: 10px;
                background-color: rgba(0,0,0,0.3);
                border-radius: 15px;
            }}
        """)

    def _setup_connections(self):
        self.search_btn.clicked.connect(self.on_search)
        self.loc_btn.clicked.connect(self.on_use_my_location)
        self.refresh_btn.clicked.connect(self.on_refresh) 
        self.open_browser_btn.clicked.connect(self.open_map_in_browser)
        self.lang_selector.currentIndexChanged.connect(self.on_lang_change)
        self.resize_map_btn.clicked.connect(self.on_resize_map)
        self.change_bg_btn.clicked.connect(self.on_change_bg)
        self.ai_assistant_btn.clicked.connect(self.on_ai_assistant)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.bg_label.resize(self.size())
        
        # Оновлення фону при зміні розміру
        if self._current_bg_path and os.path.exists(self._current_bg_path):
            pix = QtGui.QPixmap(self._current_bg_path)
            
            if pix.isNull():
                 log_message(f"ERROR: QPixmap не змогла завантажити файл: {self._current_bg_path}. Перевірте формат.")
                 return
            
            pix = pix.scaled(self.size(), QtCore.Qt.KeepAspectRatioByExpanding, QtCore.Qt.SmoothTransformation)
            self.bg_label.setPixmap(pix)
            log_message(f"INFO: Фон оновлено з файлу: {self._current_bg_path}")
        elif self._current_bg_path:
            log_message(f"ERROR: Файл фону не існує за шляхом: {self._current_bg_path}")


    # --- Map & Weather Methods ---
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
            
        except ConnectionError as e:
            self.info_label.setText(f"Помилка з'єднання: {e}")
            log_message(f"ERROR: {e}")
        except Exception as e:
            self.info_label.setText(f"Загальна помилка: {e}")
            log_message(f"FATAL: Непередбачена помилка: {e}")

    # --- Actions ---
    def on_refresh(self):
        """Оновлює дані про погоду та фон для поточної локації."""
        log_message("ACTION: Оновлення погоди.")
        self.update_weather_and_background()

    def on_search(self):
        query = self.search_input.text().strip()
        if not query: return
        
        self.search_btn.setEnabled(False) 
        self.search_btn.setText("Шукаємо...")
        
        res = geocode_address(query)
        
        self.search_btn.setEnabled(True)
        self.search_btn.setText("Search 🔍")
        
        if res:
            self.current_lat, self.current_lon, _ = res
            self.update_map()
            self.update_weather_and_background()
        else:
            QMessageBox.warning(self, "Not Found", "Не вдалося знайти місце за вашим запитом.")

    def on_use_my_location(self):
        try:
            r = requests.get(IP_API_URL, timeout=8).json()
            if r.get("status") == "success":
                self.current_lat, self.current_lon = r.get("lat"), r.get("lon")
                self.update_map()
                self.update_weather_and_background()
            else:
                 raise Exception("Не вдалося отримати координати.")
        except Exception:
            QMessageBox.warning(self, "Error", "Не вдалося отримати поточне місцезнаходження за IP.")

    def open_map_in_browser(self):
        if os.path.exists(self.map_tempfile):
            import webbrowser
            webbrowser.open(f"file:///{self.map_tempfile}")
            
    def on_lang_change(self, idx):
        self.current_lang = self.lang_selector.currentData()
        self.update_weather_and_background()

    def on_resize_map(self):
        w, ok1 = QInputDialog.getInt(self, "Map Width", "Введіть нову ширину (px):", 
                                     self.webview.width(), 400, 1400, 10)
        if not ok1: return
        h, ok2 = QInputDialog.getInt(self, "Map Height", "Введіть нову висоту (px):", 
                                     self.webview.height(), 300, 900, 10)
        if not ok2: return
        
        self.webview.setFixedSize(w, h)
        
    def on_change_bg(self):
        """Вибір користувацького фону та оновлення екрану."""
        path, _ = QFileDialog.getOpenFileName(self, "Select Background Image", 
                                              BACKGROUNDS_DIR,
                                              f"Images (*{' *'.join(SUPPORTED_EXTS)})")
        if path:
            self._current_bg_path = path 
            self.resizeEvent(None) # Примусово оновлюємо фон

    def on_ai_assistant(self):
        """Відкриває діалогове вікно AI-асистента."""
        if self.ai_assistant_dialog is None:
            self.ai_assistant_dialog = AICountryInfoDialog(parent=self)
        self.ai_assistant_dialog.show()

# ---------------- MAIN EXECUTION ----------------
def main():
    log_message("INFO: Запуск програми.")
    
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(43, 47, 51))
    palette.setColor(QtGui.QPalette.WindowText, QtCore.Qt.white)
    app.setPalette(palette)
    
    window = MapWeatherApp()
    window.show()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()