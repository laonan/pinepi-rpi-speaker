import datetime
import json
import os
from lunarcalendar import Converter, Lunar

from pinepi_speaker import config
from pinepi_speaker.tts.registry import resolve_adapter

CONFIG = os.path.join(config.BASE_DIR, "data", "birthdays.json")

_adapter = None

def say(text):
    global _adapter
    if _adapter is None:
        _adapter = resolve_adapter()
        _adapter.start()
    _adapter.speak(text)

def is_today_solar(month, day):
    today = datetime.date.today()
    return today.month == month and today.day == day

def is_today_lunar(month, day):
    today = datetime.date.today()
    lunar = Lunar(today.year, month, day)
    solar = Converter.Lunar2Solar(lunar)
    return today == datetime.date(solar.year, solar.month, solar.day)

def is_tomorrow_solar(month, day):
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    return tomorrow.month == month and tomorrow.day == day

def is_tomorrow_lunar(month, day):
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    lunar = Lunar(tomorrow.year, month, day)
    solar = Converter.Lunar2Solar(lunar)
    return tomorrow == datetime.date(solar.year, solar.month, solar.day)

def check_birthdays():
    today = datetime.date.today()
    print("Checking:", today)

    with open(CONFIG, "r") as f:
        data = json.load(f)

    for person in data:
        name = person["name"]
        typ = person["type"]
        month = person["month"]
        day = person["day"]
        msg = person.get("msg", f"{name}生日")

        try:
            # 当天提醒
            if typ == "solar" and is_today_solar(month, day):
                say(msg)
            elif typ == "lunar" and is_today_lunar(month, day):
                say(msg)

            # 提前一天提醒
            if typ == "solar" and is_tomorrow_solar(month, day):
                say(f"明天是{name}的生日，{msg}")
            elif typ == "lunar" and is_tomorrow_lunar(month, day):
                say(f"明天是{name}的生日，{msg}")

        except Exception as e:
            print(f"Error for {name}:", e)

if __name__ == "__main__":
    check_birthdays()
