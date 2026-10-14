
from pathlib import Path
from datetime import datetime
import re
import subprocess
import webbrowser
import urllib.parse
import time

import joblib
import pyttsx3
import requests


BASE_DIR = Path(__file__).resolve().parent.parent
MODEL_FILE = BASE_DIR / "model" / "intent_model.pkl"


class PersonalAssistant:

    def __init__(self):
        if not MODEL_FILE.exists():
            raise FileNotFoundError(
                "ML model not found. Run: python src/train_model.py"
            )

        self.model = joblib.load(MODEL_FILE)

        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 170)

    def speak(self, text):
        print(f"Assistant: {text}")
        self.engine.say(text)
        self.engine.runAndWait()

    def predict_intent(self, text):
        return self.model.predict([text])[0]

    @staticmethod
    def open_application(app):
        commands = {
            "chrome": ["cmd", "/c", "start", "", "chrome"],
            "notepad": ["notepad.exe"],
            "calculator": ["calc.exe"],
        }

        command = commands.get(app)

        if not command:
            return False

        try:
            subprocess.Popen(command)
            return True
        except Exception:
            return False

    @staticmethod
    def extract_search_query(text, intent):
        patterns = {
            "web_search": [
                r"search(?: for)?\s+(.+)",
                r"google\s+(.+)",
                r"find information(?: about| on)?\s+(.+)",
            ],
            "search_youtube": [
                r"search youtube(?: for)?\s+(.+)",
                r"youtube\s+(.+)",
                r"find videos(?: about| on)?\s+(.+)",
            ],
        }

        for pattern in patterns.get(intent, []):
            match = re.search(pattern, text, re.IGNORECASE)

            if match:
                return match.group(1).strip()

        return text.strip()

    # MUSIC INTENT
    def play_music(self, text):
        query = re.sub(
            r"\b(play|music|song|songs|listen to|start)\b",
            "",
            text,
            flags=re.IGNORECASE
        ).strip()

        if not query:
            query = "popular music"

        url = (
            "https://www.youtube.com/results?search_query="
            + urllib.parse.quote_plus(query)
        )

        webbrowser.open(url)
        self.speak(f"Searching YouTube for {query}.")

    # WEATHER INTENT
    def get_weather(self, text):
        match = re.search(
            r"(?:weather|temperature|forecast)"
            r"(?:\s+(?:today|right now|currently))?"
            r"\s+(?:in|for|of)\s+(.+)",
            text,
            re.IGNORECASE
        )

        if not match:
            self.speak(
                "Please specify a city, for example, "
                "weather in Delhi."
            )
            return

        city = match.group(1).strip(" ?.!,")
        
        try:
            # Find city coordinates
            geo_url = (
                "https://geocoding-api.open-meteo.com/v1/search"
            )

            geo_response = requests.get(
                geo_url,
                params={
                    "name": city,
                    "count": 1,
                    "language": "en",
                    "format": "json"
                },
                timeout=10
            )

            geo_response.raise_for_status()

            locations = geo_response.json().get("results", [])

            if not locations:
                self.speak(f"I could not find the city {city}.")
                return

            location = locations[0]

            latitude = location["latitude"]
            longitude = location["longitude"]
            city_name = location["name"]

            # Fetch current weather
            weather_url = (
                "https://api.open-meteo.com/v1/forecast"
            )

            weather_response = requests.get(
                weather_url,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,"
                        "relative_humidity_2m,"
                        "wind_speed_10m,"
                        "weather_code"
                    ),
                    "timezone": "auto"
                },
                timeout=10
            )

            weather_response.raise_for_status()

            current = weather_response.json()["current"]

            temperature = current["temperature_2m"]
            humidity = current["relative_humidity_2m"]
            wind = current["wind_speed_10m"]
            weather_code = current["weather_code"]

            descriptions = {
                0: "clear sky",
                1: "mainly clear",
                2: "partly cloudy",
                3: "overcast",
                45: "foggy",
                48: "foggy",
                51: "light drizzle",
                53: "moderate drizzle",
                55: "heavy drizzle",
                61: "light rain",
                63: "moderate rain",
                65: "heavy rain",
                71: "light snowfall",
                73: "moderate snowfall",
                75: "heavy snowfall",
                80: "rain showers",
                81: "moderate rain showers",
                82: "heavy rain showers",
                95: "thunderstorm",
                96: "thunderstorm with hail",
                99: "thunderstorm with heavy hail"
            }

            condition = descriptions.get(
                weather_code,
                "weather conditions unavailable"
            )

            self.speak(
                f"Current weather in {city_name}. "
                f"Condition: {condition}. "
                f"Temperature: {temperature} degrees Celsius. "
                f"Humidity: {humidity} percent. "
                f"Wind speed: {wind} kilometers per hour."
            )

        except (
            requests.RequestException,
            KeyError,
            ValueError,
            TypeError
        ):
            self.speak(
                "Sorry, I could not retrieve the weather. "
                "Please check your internet connection."
            )

    def execute(self, text, intent):
        normalized = text.lower().strip()

        if intent == "greeting":
            self.speak("Hello. How can I help you?")

        elif intent == "open_chrome":
            if self.open_application("chrome"):
                self.speak("Opening Chrome.")
            else:
                webbrowser.open("https://www.google.com")
                self.speak("Opening the web browser.")

        elif intent == "open_notepad":
            if self.open_application("notepad"):
                self.speak("Opening Notepad.")
            else:
                self.speak("I could not open Notepad.")

        elif intent == "open_calculator":
            if self.open_application("calculator"):
                self.speak("Opening Calculator.")
            else:
                self.speak("I could not open Calculator.")

        elif intent == "web_search":
            query = self.extract_search_query(text, intent)

            url = (
                "https://www.google.com/search?q="
                + urllib.parse.quote_plus(query)
            )

            webbrowser.open(url)
            self.speak(f"Searching the web for {query}.")

        elif intent == "open_youtube":
            webbrowser.open("https://www.youtube.com")
            self.speak("Opening YouTube.")

        elif intent == "search_youtube":
            query = self.extract_search_query(text, intent)

            url = (
                "https://www.youtube.com/results?search_query="
                + urllib.parse.quote_plus(query)
            )

            webbrowser.open(url)
            self.speak(f"Searching YouTube for {query}.")

        # NEW: MUSIC
        elif intent == "music":
            self.play_music(text)

        # NEW: WEATHER
        elif intent == "weather":
            self.get_weather(text)

        elif intent == "time":
            current_time = datetime.now().strftime("%I:%M %p")
            self.speak(f"The current time is {current_time}.")

        elif intent == "date":
            current_date = datetime.now().strftime("%d %B %Y")
            self.speak(f"Today's date is {current_date}.")

        elif intent == "calculator":
            self.speak(
                "For calculations, please use the Windows Calculator."
            )

        elif intent == "exit":
            self.speak("Goodbye.")
            return False

        else:
            self.speak(
                "Sorry, I do not understand that command yet."
            )

        return True
