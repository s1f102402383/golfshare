import os
import requests
from .models import StationCache, TravelTimeCache


RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

TRANSPORT_HOST = "navitime-transport.p.rapidapi.com"
ROUTE_HOST = "navitime-route-totalnavi.p.rapidapi.com"


def get_station_id(station_name):
    url = f"https://{TRANSPORT_HOST}/transport_node"
    headers = {
        "x-rapidapi-host": TRANSPORT_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    params = {"word": station_name}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return None

    items = response.json().get("items", [])
    for item in items:
        if "station" in item.get("types", []):
            return item["id"]
    return None


def get_travel_time(start_id, goal_id, start_time):
    url = f"https://{ROUTE_HOST}/route_transit"
    headers = {
        "x-rapidapi-host": ROUTE_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }
    params = {
        "start": start_id,
        "goal": goal_id,
        "goal_time": start_time,
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return None, None

    items = response.json().get("items", [])
    if not items:
        return None, None

    move = items[0]["summary"]["move"]
    return move["time"], move["from_time"]



def get_station_id_cached(station_name):
    cache = StationCache.objects.filter(station_name=station_name).first()
    if cache:
        return cache.station_id

    station_id = get_station_id(station_name)
    if station_id:
        StationCache.objects.create(
            station_name=station_name,
            station_id=station_id,
        )
    return station_id


def get_travel_time_cached(start_id, goal_id, goal_time):
    cache = TravelTimeCache.objects.filter(
        start_id=start_id, goal_id=goal_id, goal_time=goal_time
    ).first()
    if cache:
        return cache.minutes, cache.from_time

    minutes, from_time = get_travel_time(start_id, goal_id, goal_time)
    if minutes is not None:
        TravelTimeCache.objects.create(
            start_id=start_id,
            goal_id=goal_id,
            goal_time=goal_time,
            minutes=minutes,
            from_time=from_time,
        )
    return minutes, from_time
