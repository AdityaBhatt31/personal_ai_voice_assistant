"""Recreate the voice assistant intent dataset from balanced, supported examples."""
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "dataset" / "intents.csv"

EXAMPLES = {
    "greeting": [
        "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
        "hello Deva", "hey there", "how are you", "how is it going", "howdy",
        "namaste", "kaise ho", "hello assistant", "hi there", "good to see you",
    ],
    "open_chrome": [
        "open chrome", "launch chrome", "start chrome", "open my browser",
        "open google chrome", "launch the browser", "start web browser",
        "please open chrome", "open browser for me", "go to chrome", "browser kholo",
        "chrome kholo",
    ],
    "open_notepad": [
        "open notepad", "launch notepad", "start notepad", "open text editor",
        "open a text file", "launch the text editor", "please open notepad",
        "start the scratchpad", "notepad kholo", "text editor kholo",
    ],
    "open_calculator": [
        "open calculator", "launch calculator", "start calculator", "open calc",
        "open the calculator app", "start math calculator", "please open calculator",
        "calculator kholo", "calc chalao", "open my calculator",
    ],
    "web_search": [
        "search the web", "search for python", "look up machine learning",
        "find information about climate change", "google python programming",
        "search who is the father of computer", "what is data structures and algorithms",
        "who is Ada Lovelace", "find recent space news", "look up the history of India",
        "search for a recipe for dal", "tell me about photosynthesis",
        "what is the capital of Japan", "why is the sky blue", "explain cloud computing",
        "search information about solar energy", "internet par python search karo",
        "DSA kya hota hai", "computer ke father kaun hain", "mujhe machine learning ke bare mein batao",
    ],
    "open_youtube": [
        "open youtube", "launch youtube", "go to youtube", "open the youtube website",
        "start youtube", "youtube kholo", "youtube open karo", "take me to youtube",
        "visit youtube", "open youtube for me",
    ],
    "search_youtube": [
        "search youtube for python tutorials", "find videos about drawing on youtube",
        "search for cooking videos on youtube", "find coding videos on youtube",
        "look up travel vlogs on youtube", "youtube par python videos dhoondo",
        "youtube pe cooking search karo", "find a video about space on youtube",
        "search youtube for guitar lessons", "show me videos about cricket",
        "find yoga videos on youtube", "search youtube for science experiments",
    ],
    "time": [
        "what time is it", "tell me the time", "current time", "what is the time now",
        "check the clock", "time right now", "what is the local time", "clock batao",
        "abhi kitne baje hain", "time kya hua hai", "tell me the current time please",
        "can you check the time",
    ],
    "date": [
        "what is today's date", "tell me the date", "what date is it today",
        "current date", "show today's date", "which day is it today", "date today please",
        "aaj ki date kya hai", "aaj ka din kya hai", "today's date batao",
        "what is the date today", "can you tell me today's date",
    ],
    "calculator": [
        "calculate 2 plus 2", "what is 15 times 4", "calculate 100 divided by 5",
        "multiply 12 by 8", "what is 50 minus 20", "add 35 and 47", "divide 144 by 12",
        "calculate 9 times 9", "what is 10 plus 17", "subtract 8 from 30",
        "calculate 25 multiplied by 4", "what is 81 divided by 9", "12 plus 14 kitna hota hai",
        "50 ko 5 se divide karo", "calculate 7 times 6", "what is 100 minus 33",
    ],
    "exit": [
        "exit", "quit", "goodbye", "bye", "stop assistant", "close the assistant",
        "turn off assistant", "shut down", "end this session", "that's all goodbye",
        "band karo", "alvida", "stop now", "close Deva", "see you later",
    ],
    "weather": [],
    "alarm": [],
    "music": [],
}

cities = ["Delhi", "Mumbai", "London", "New York", "Tokyo"]
weather_forms = [
    "what is the weather in {city}", "weather forecast for {city}",
    "is it raining in {city}", "tell me the temperature in {city}",
    "will it be sunny in {city} today", "check weather for {city}",
]
EXAMPLES["weather"] = [form.format(city=city) for city in cities for form in weather_forms]
EXAMPLES["weather"] += ["mausam kaisa hai Delhi mein", "Mumbai ka weather batao", "weather in Paris"]

times = ["6 am", "6:30 am", "7 am", "7:15 am", "7:30 am", "8 am", "8:30 am", "9 am",
         "10 pm", "11:45 pm", "18:30", "07:00", "5:30 am", "12 pm"]
alarm_forms = [
    "set an alarm for {time}", "wake me up at {time}", "alarm for {time}",
    "set my alarm at {time}", "please wake me at {time}",
]
EXAMPLES["alarm"] = [form.format(time=t) for t in times for form in alarm_forms]
EXAMPLES["alarm"] += [
    "set an alarm in 10 minutes", "wake me up in 5 minutes", "alarm after 2 hours",
    "set alarm for 20 minutes from now", "wake me in 1 hour", "set an alarm for tomorrow at 7 am",
    "set an alarm for 6:30 am tomorrow", "subah 7 baje alarm lagao", "kal subah 6 baje jagana",
    "raat 10 baje ka alarm lagao", "5 minute baad alarm bajana", "mujhe 15 minute mein jagao",
]

genres = ["lo-fi", "jazz", "rock", "pop", "classical", "hip hop", "romantic", "workout",
          "relaxing", "blues", "country", "electronic", "Hindi", "Punjabi", "devotional",
          "Arijit Singh", "Taylor Swift", "old Bollywood"]
music_forms = [
    "play {style}", "play some {style} music", "listen to {style}",
    "put on {style} songs", "start playing {style}",
]
EXAMPLES["music"] = [form.format(style=style) for style in genres for form in music_forms]
EXAMPLES["music"] += [
    "play Shape of You", "play songs by Ed Sheeran", "play Tum Hi Ho", "play relaxing music for me",
    "mujhe Arijit Singh ke gaane sunao", "kuch Hindi music chalao", "gaana bajao",
    "koi romantic song play karo", "lofi music sunao", "play music on youtube",
]

rows = []
seen = set()
for intent, phrases in EXAMPLES.items():
    for phrase in phrases:
        text = " ".join(phrase.split()).strip()
        key = text.casefold()
        if text and key not in seen:
            rows.append((text, intent))
            seen.add(key)

OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["text", "intent"])
    writer.writerows(rows)

counts = {intent: sum(label == intent for _, label in rows) for intent in EXAMPLES}
print(f"Rebuilt {len(rows)} unique examples across {len(counts)} intents: {counts}")
print(f"Saved: {OUT}")
