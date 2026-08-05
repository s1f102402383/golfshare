import os
import requests

headers = {
    "x-rapidapi-host": "navitime-route-totalnavi.p.rapidapi.com",
    "x-rapidapi-key": os.environ.get("RAPIDAPI_KEY")
}

params = {
    "start": "00005199",
    "goal": "00005069",
    "start_time": "2026-08-10T08:00:00"
}

url = "https://navitime-route-totalnavi.p.rapidapi.com/route_transit"

response = requests.get(url, headers=headers, params=params)
data = response.json()

summary = data["items"][0]["summary"]["move"]
print("所要時間:", summary["time"], "分")
print("乗換回数:", summary["transit_count"], "回")