"""Web API for the Personal AI Voice Assistant.

Run from the project root:  uvicorn main:app --reload
Then open:                  http://127.0.0.1:8000
"""
import ast
import operator
import re
import hashlib
import hmac
import secrets
import os
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.assistant import PersonalAssistant  # only its static helper is used

BASE_DIR = Path(__file__).resolve().parent
MODEL_FILE = BASE_DIR / "model" / "intent_model.pkl"
FRONTEND_DIR = BASE_DIR / "frontend"
SESSION_COOKIE = "deva_session"
load_dotenv(BASE_DIR / ".env")

# Below this confidence the assistant says "I did not understand".
CONFIDENCE_THRESHOLD = 0.45

# True  = "open chrome / notepad / calculator" opens on THIS computer
#         (correct when you run the server on your own PC).
# False = use this when the server is hosted online; those commands are declined.
RUN_APPS_ON_SERVER = True

WEATHER_DESCRIPTIONS = {
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
    99: "thunderstorm with heavy hail",
}

if not MODEL_FILE.exists():
    raise RuntimeError("Model not found. Run: python src/train_model.py")

model = joblib.load(MODEL_FILE)  # loaded once, when the server starts
ASSISTANT_NAME = "Deva"

app = FastAPI(title=f"{ASSISTANT_NAME} - Personal AI Voice Assistant")


class Query(BaseModel):
    text: str


class Credentials(BaseModel):
    email: str
    password: str


class ChatQuery(BaseModel):
    text: str
    conversation_id: int | None = None


class MySQLConnection:
    def __init__(self):
        import pymysql
        name = os.getenv("MYSQL_DATABASE", "personal_ai_voice_assistant")
        if not re.fullmatch(r"[A-Za-z0-9_]+", name):
            raise RuntimeError("MYSQL_DATABASE may contain only letters, numbers, and underscores.")
        opts = dict(host=os.getenv("MYSQL_HOST", "127.0.0.1"), port=int(os.getenv("MYSQL_PORT", "3306")),
                    user=os.getenv("MYSQL_USER", "root"), password=os.getenv("MYSQL_PASSWORD", ""),
                    charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
        self.conn = pymysql.connect(**opts, database=name, autocommit=False)

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, tb):
        if exc_type is None: self.conn.commit()
        else: self.conn.rollback()
        self.conn.close()

    def execute(self, sql, params=()):
        cursor = self.conn.cursor()
        cursor.execute(sql.replace("?", "%s"), params)
        return cursor


def db():
    return MySQLConnection()


def ensure_database():
    import pymysql
    name = os.getenv("MYSQL_DATABASE", "personal_ai_voice_assistant")
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise RuntimeError("MYSQL_DATABASE may contain only letters, numbers, and underscores.")
    conn = pymysql.connect(host=os.getenv("MYSQL_HOST", "127.0.0.1"),
                           port=int(os.getenv("MYSQL_PORT", "3306")),
                           user=os.getenv("MYSQL_USER", "root"), password=os.getenv("MYSQL_PASSWORD", ""),
                           charset="utf8mb4", autocommit=True)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    finally:
        conn.close()


def init_db():
    with db() as conn:
        for statement in (
            """CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY AUTO_INCREMENT, email VARCHAR(254) NOT NULL UNIQUE,
                password_hash CHAR(64) NOT NULL, salt CHAR(32) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS sessions (
                token_hash CHAR(64) PRIMARY KEY, user_id BIGINT NOT NULL,
                expires_at BIGINT NOT NULL, FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS conversations (
                id BIGINT PRIMARY KEY AUTO_INCREMENT, user_id BIGINT NOT NULL,
                title VARCHAR(255) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            """CREATE TABLE IF NOT EXISTS messages (
                id BIGINT PRIMARY KEY AUTO_INCREMENT, conversation_id BIGINT NOT NULL,
                role VARCHAR(16) NOT NULL, content TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
        ):
            conn.execute(statement)


ensure_database()
init_db()


def password_digest(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 310000).hex()


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please log in.")
    with db() as conn:
        row = conn.execute("SELECT u.id,u.email FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>?",
                           (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Session expired. Please log in again.")
    return row


def set_session(response: Response, user_id: int):
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO sessions VALUES(?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + 60*60*24*30))
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax", secure=False, max_age=60*60*24*30)


@app.post("/api/auth/register")
def register(body: Credentials, response: Response):
    email = body.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(body.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    salt = secrets.token_hex(16)
    try:
        with db() as conn:
            cur = conn.execute("INSERT INTO users(email,password_hash,salt) VALUES(?,?,?)", (email, password_digest(body.password, salt), salt))
            user_id = cur.lastrowid
    except Exception as exc:
        if exc.__class__.__name__ == "IntegrityError":
            raise HTTPException(409, "An account with this email already exists.")
        raise
    set_session(response, user_id)
    return {"email": email}


@app.post("/api/auth/login")
def login(body: Credentials, response: Response):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    if not row or not hmac.compare_digest(password_digest(body.password, row["salt"]), row["password_hash"]):
        raise HTTPException(401, "Email or password is incorrect.")
    set_session(response, row["id"])
    return {"email": row["email"]}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request):
    user = current_user(request)
    return {"email": user["email"]}


@app.get("/api/conversations")
def conversations(request: Request):
    user = current_user(request)
    with db() as conn:
        rows = conn.execute("SELECT id,title,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC", (user["id"],)).fetchall()
    return [dict(row) for row in rows]


@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: int, request: Request):
    user = current_user(request)
    with db() as conn:
        deleted = conn.execute(
            "DELETE FROM conversations WHERE id=? AND user_id=?",
            (conversation_id, user["id"]),
        )
        if deleted.rowcount == 0:
            raise HTTPException(404, "Conversation not found.")
    return {"deleted": True, "conversation_id": conversation_id}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: int, request: Request):
    user = current_user(request)
    with db() as conn:
        row = conn.execute("SELECT id,title FROM conversations WHERE id=? AND user_id=?", (conversation_id,user["id"])).fetchone()
        if not row: raise HTTPException(404, "Conversation not found.")
        messages = conn.execute("SELECT role,content FROM messages WHERE conversation_id=? ORDER BY id", (conversation_id,)).fetchall()
    return {"id":row["id"],"title":row["title"],"messages":[dict(m) for m in messages]}


# ---------------------------------------------------------------- helpers
def open_url(url: str, label: str) -> dict:
    """The browser (frontend) opens links, not the server."""
    return {"type": "open_url", "url": url, "label": label}


def extract_query(text: str) -> str:
    """'search Python on google' -> 'Python'. Returns '' if nothing to search."""
    q = text.strip()
    q = re.sub(
        r"^(please\s+)?(search|google|find|look\s+up|look\s+for)\s+"
        r"((youtube|videos?|information)\s+)*(for\s+|about\s+|on\s+)?",
        "", q, flags=re.I,
    )
    q = re.sub(r"\s+(on|in|at)\s+(google|youtube|the\s+web|web)\s*$", "", q, flags=re.I)
    q = re.sub(r"^(youtube|google)\s+", "", q, flags=re.I).strip()
    if q.lower() in {"", "search", "find", "youtube", "google", "web", "the web", "on google", "on youtube"}:
        return ""
    return q


def keyword_intent(text: str):
    """Search words decide the intent, so phrases like 'search X in Google' never get missed."""
    t = text.lower()
    if re.search(r"\b(alarm|wake\s+me\s+up|wake\s+up)\b", t) and not re.search(r"\b(search|google|look up)\b", t):
        return "alarm"
    if "youtube" in t and re.search(r"\b(search|find|look up)\b", t):
        return "search_youtube"
    if (re.search(r"\b(play|listen to|put on|start playing|queue)\b", t)
            or (re.search(r"\b(start|turn on)\b", t) and re.search(r"\b(music|songs?|tracks?|playlist)\b", t))
            or (re.search(r"\b(bajao|sunao|chalao)\b", t) and re.search(r"\b(music|songs?|tracks?|playlist|gaana|gaane)\b", t))):
        return "music"
    if re.search(r"\b(search|google|look up)\b", t):
        return "web_search"
    return None


def web_search_results(query: str):
    """Search the web through DDGS metasearch; no API key is needed."""
    try:
        from ddgs import DDGS
        items = DDGS(timeout=10).text(query, region="in-en", safesearch="moderate", max_results=3, backend="auto")
        results = [
            {"title": item.get("title", "Search result"),
             "snippet": item.get("body", "").strip(),
             "url": item.get("href", "")}
            for item in items if item.get("href")
        ]
        return results, None
    except Exception:
        return None, "Web search could not be reached. Check your internet connection and make sure the ddgs dependency is installed."


def choose_best_result(query: str, results: list[dict]):
    """Prefer the result whose title and snippet best match the question terms."""
    ignored = {"what", "who", "where", "when", "which", "is", "are", "was", "were",
               "the", "a", "an", "of", "to", "in", "for", "on", "and", "search", "google"}
    terms = set(re.findall(r"[a-z0-9]+", query.lower())) - ignored
    if not terms:
        return results[0]

    def score(result):
        title = result.get("title", "").lower()
        snippet = result.get("snippet", "").lower()
        title_terms = set(re.findall(r"[a-z0-9]+", title))
        body_terms = set(re.findall(r"[a-z0-9]+", snippet))
        title_match = len(terms & title_terms) / len(terms)
        body_match = len(terms & body_terms) / len(terms)
        phrase_bonus = 1 if query.lower().strip(" ?.! ") in title else 0
        return title_match * 4 + body_match * 2 + phrase_bonus

    return max(results, key=score)


def music_query(text: str) -> str:
    """Keep the requested artist or track while removing the command phrasing."""
    query = re.sub(r"^(please\s+)?(can you\s+)?(play me|play|listen to|put on|start(?: playing)?|queue)\s+", "", text, flags=re.I)
    query = re.sub(r"^(mujhe|kuch|koi)\s+", "", query, flags=re.I)
    query = re.sub(r"\s+(on youtube|for me|please)$", "", query, flags=re.I)
    query = re.sub(r"\s+(?:ke\s+)?(?:gaane?|gana|gaana|music|songs?|tracks?)?\s*(?:sunao|bajao|chalao|play karo)$", "", query, flags=re.I)
    query = re.sub(r"^(songs?|tracks?|music)\s+by\s+", "", query, flags=re.I)
    query = re.sub(r"^(?:a\s+)?(?:song|track)\s+(?:called\s+)?", "", query, flags=re.I)
    query = re.sub(r"\b(some|a few|the best|best)\b", "", query, flags=re.I)
    query = re.sub(r"\s+(music|songs?|tracks?|playlist|gaane?|gana|gaana)$", "", query, flags=re.I)
    query = query.strip(" ,.!?-")
    return query or "popular music"


WEATHER_FILLER = {
    "check", "tell", "me", "the", "what", "whats", "is", "how", "about", "today", "now",
    "weather", "mausam", "ka", "ki", "ke", "batao", "please", "forecast", "temperature",
    "report", "right", "currently", "tomorrow", "of", "in", "for", "at", "like",
}


def weather_city(text: str) -> str:
    """'whats the weather in Delhi today' -> 'Delhi'. 'check doiwala weather' -> 'doiwala'."""
    match = re.search(r"\b(?:in|for|of|at)\s+(.+)$", text.strip(), flags=re.I)
    if not match:
        # No preposition: keep the words that are not weather filler, e.g. "check doiwala weather"
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
        return " ".join(w for w in words if w.lower() not in WEATHER_FILLER)
    city = re.sub(
        r"\s+(today|tomorrow|tonight|right now|now|currently|please)$",
        "", match.group(1).strip(" ?.!,"), flags=re.I,
    )
    return city.strip(" ?.!,")


def get_weather(text: str) -> str:
    """Current weather for the city in the sentence, using Open-Meteo (no API key)."""
    city = weather_city(text)
    if not city:
        return "Please specify a city, for example: weather in Delhi."

    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1, "language": "en", "format": "json"},
            timeout=10,
        )
        geo.raise_for_status()
        locations = geo.json().get("results", [])
        if not locations:
            return f"I could not find the city {city}."

        location = locations[0]

        forecast = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": location["latitude"],
                "longitude": location["longitude"],
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "timezone": "auto",
            },
            timeout=10,
        )
        forecast.raise_for_status()
        current = forecast.json()["current"]

        condition = WEATHER_DESCRIPTIONS.get(current["weather_code"], "weather conditions unavailable")
        return (
            f"Current weather in {location['name']}. "
            f"Condition: {condition}. "
            f"Temperature: {current['temperature_2m']} degrees Celsius. "
            f"Humidity: {current['relative_humidity_2m']} percent. "
            f"Wind speed: {current['wind_speed_10m']} kilometers per hour."
        )

    except (requests.RequestException, KeyError, ValueError, TypeError):
        return "Sorry, I could not retrieve the weather. Please check your internet connection."


_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval(node.operand)
    raise ValueError("unsupported expression")


def calculate(text: str):
    """'calculate 10 multiplied by 5' -> 50. Uses ast, never eval()."""
    expr = text.lower().replace(",", "")
    for words, symbol in (
        (r"multiplied\s+by|times|\bx\b", "*"),
        (r"divided\s+by", "/"),
        (r"plus", "+"),
        (r"minus", "-"),
    ):
        expr = re.sub(words, f" {symbol} ", expr)
    match = re.search(r"\d+(?:\.\d+)?(?:\s*[+\-*/]\s*\d+(?:\.\d+)?)+", expr)
    if not match:
        return None
    try:
        value = _eval(ast.parse(match.group(0), mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None
    return int(value) if float(value).is_integer() else round(value, 6)


def alarm_time(text: str):
    """'wake me up at 6:30 am tomorrow' -> '06:30'. Returns None if no time found."""
    m = re.search(r"\b(\d{1,2})(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?)\b", text, flags=re.I)
    if not m:
        m = re.search(r"\b(\d{1,2}):([0-5]\d)\b", text)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2))
            return f"{hour:02d}:{minute:02d}" if hour <= 23 else None
    if not m:
        m = re.search(r"\b(\d{1,2})(?::([0-5]\d))?\s*(?:baje|bajey)\b", text, flags=re.I)
        if m:
            hour, minute = int(m.group(1)), int(m.group(2) or 0)
            if re.search(r"\b(shaam|sham|evening|raat|night)\b", text, flags=re.I) and 1 <= hour < 12:
                hour += 12
            elif re.search(r"\b(subah|morning)\b", text, flags=re.I) and hour == 12:
                hour = 0
            return f"{hour:02d}:{minute:02d}" if hour <= 23 else None
    if not m:
        m = re.search(r"\bat\s+(\d{1,2})(?::([0-5]\d))?\b", text, flags=re.I)
        if not m:
            return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = ((m.group(3) or "") if m.re.groups >= 3 else "").lower().replace(".", "")
    if meridiem and hour > 12:
        return None
    if meridiem.startswith("p") and hour < 12:
        hour += 12
    elif meridiem.startswith("a") and hour == 12:
        hour = 0
    if hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def alarm_target(text: str, now: datetime | None = None):
    """Resolve relative and clock-time alarms to the next local datetime."""
    now = now or datetime.now()
    relative = re.search(
        r"\b(?:in|after)\s+(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b|"
        r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\s*(?:from now|later|baad)\b",
        text, flags=re.I,
    )
    if relative:
        amount = int(relative.group(1) or relative.group(3))
        unit = (relative.group(2) or relative.group(4)).lower()
        if amount <= 0 or amount > 10080:
            return None
        if unit.startswith(("hour", "hr")):
            return now + timedelta(hours=amount)
        if unit.startswith(("second", "sec")):
            return now + timedelta(seconds=amount)
        return now + timedelta(minutes=amount)

    time_24 = alarm_time(text)
    if not time_24:
        return None
    hour, minute = map(int, time_24.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if re.search(r"\b(tomorrow|tmrw|kal)\b", text, flags=re.I):
        target += timedelta(days=1)
    elif target <= now:
        target += timedelta(days=1)
    return target


# ---------------------------------------------------------------- intent -> reply
def run_intent(text: str, intent: str) -> dict:
    """Web version of PersonalAssistant.execute(): returns data instead of speaking."""
    reply, action, exit_now = "", None, False
    sources = []
    now = datetime.now()

    if intent == "greeting":
        reply = f"Hello, I am {ASSISTANT_NAME}. How can I help you?"

    elif intent in ("open_chrome", "open_notepad", "open_calculator"):
        app_name = intent.replace("open_", "")
        if RUN_APPS_ON_SERVER and PersonalAssistant.open_application(app_name):
            reply = f"Opening {app_name.capitalize()}."
        elif intent == "open_chrome":
            reply = "Opening Google in a new tab."
            action = open_url("https://www.google.com", "Open Google")
        else:
            reply = f"I could not open {app_name.capitalize()} from here."

    elif intent == "web_search":
        query = extract_query(text)
        if query:
            results, error = web_search_results(query)
            if error:
                reply = error
            elif not results:
                reply = f"No search results found for: {query}"
            else:
                best = choose_best_result(query, results)
                sources = [best]
                reply = f"Here's a useful result about {query}:\n\n{best['snippet']}"
        else:
            reply = "What should I search for? Try: search Python."

    elif intent == "open_youtube":
        reply = "Opening YouTube."
        action = open_url("https://www.youtube.com", "Open YouTube")

    elif intent == "search_youtube":
        query = extract_query(text)
        if query:
            url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
            reply = f"Searching YouTube for {query}."
            action = open_url(url, "Open YouTube results")
        else:
            reply = "What should I search on YouTube? Try: search Python tutorials on youtube."

    elif intent == "music":
        query = music_query(text)
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
        reply = f"I found YouTube results for {query}. Choose a video to start playback."
        action = open_url(url, "Choose and play on YouTube")

    elif intent == "weather":
        reply = get_weather(text)

    elif intent == "alarm":
        target = alarm_target(text, now)
        if target:
            label = target.strftime("%I:%M %p")
            if target.date() != now.date():
                label += " tomorrow"
            reply = f"Alarm set for {label}. Keep this browser page open for it to ring."
            action = {"type": "set_alarm", "target": target.isoformat(timespec="seconds"), "label": f"Alarm for {label}"}
        else:
            reply = "What time should I set the alarm for? Try: set an alarm for 7 am."

    elif intent == "time":
        reply = f"The current time is {now.strftime('%I:%M %p')}."

    elif intent == "date":
        reply = f"Today's date is {now.strftime('%d %B %Y')}."

    elif intent == "calculator":
        result = calculate(text)
        reply = (f"The answer is {result}." if result is not None
                 else "I could not read that calculation. Try: calculate 12 times 5.")

    elif intent == "exit":
        reply, exit_now = "Goodbye.", True

    else:
        reply = "Sorry, I do not understand that command yet."

    return {"reply": reply, "action": action, "exit": exit_now, "sources": sources}


# ---------------------------------------------------------------- endpoints
@app.get("/api/health")
def health():
    return {"status": "ok", "intents": [str(c) for c in model.classes_]}


@app.post("/api/chat")
def chat(query: ChatQuery, request: Request):
    user = current_user(request)
    text = query.text.strip()
    # Remove the name so "Deva what time is it" is classified as "what time is it".
    clean_text = re.sub(rf"\b{re.escape(ASSISTANT_NAME)}\b[,!?.]?", "", text, flags=re.I).strip()
    if not clean_text:
        clean_text = "hello"  # only the name was said, so treat it as a greeting
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty.")

    probabilities = model.predict_proba([clean_text])[0]
    best = int(probabilities.argmax())
    intent = str(model.classes_[best])
    confidence = round(float(probabilities[best]), 3)

    forced = keyword_intent(clean_text)
    if forced:
        intent, confidence = forced, 1.0
    elif (re.match(r"^(what|who|where|when|which)\s+(is|are|was|were)\b", clean_text, flags=re.I)
          and intent not in {"time", "date", "weather", "calculator", "alarm"}):
        # Route factual questions such as "What is DSA?" to the answer lookup,
        # even when the intent classifier has not seen that exact topic before.
        intent, confidence = "web_search", 1.0

    if confidence < CONFIDENCE_THRESHOLD:
        result = {
            "text": text, "intent": "unknown", "confidence": confidence,
            "reply": "Sorry, I do not understand that command yet.",
            "action": None, "exit": False,
        }
    else:
        result = {"text": text, "intent": intent, "confidence": confidence, **run_intent(clean_text, intent)}
    with db() as conn:
        conversation_id = query.conversation_id
        if conversation_id is not None:
            exists = conn.execute("SELECT 1 FROM conversations WHERE id=? AND user_id=?", (conversation_id,user["id"])).fetchone()
            if not exists: raise HTTPException(404, "Conversation not found.")
        else:
            title = text[:60] + ("…" if len(text) > 60 else "")
            conversation_id = conn.execute("INSERT INTO conversations(user_id,title) VALUES(?,?)", (user["id"],title)).lastrowid
        conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)", (conversation_id,"user",text))
        conn.execute("INSERT INTO messages(conversation_id,role,content) VALUES(?,?,?)", (conversation_id,"assistant",result["reply"]))
        conn.execute("UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (conversation_id,))
    result["conversation_id"] = conversation_id
    return result


# Serve the frontend. Keep this LAST so it does not hide the /api routes.
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
