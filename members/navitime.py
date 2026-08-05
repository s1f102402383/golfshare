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
        "start_time": start_time,
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return None

    items = response.json().get("items", [])#get("items", [])もし仮にこれは存在しないキーをしていた場合に空のリストを返すもの
    if not items:
        return None

    return items[0]["summary"]["move"]["time"]





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


def get_travel_time_cached(start_id, goal_id, start_time):
    cache = TravelTimeCache.objects.filter(
        start_id=start_id, goal_id=goal_id
    ).first()
    if cache:
        return cache.minutes

    minutes = get_travel_time(start_id, goal_id, start_time)
    if minutes is not None:
        TravelTimeCache.objects.create(
            start_id=start_id,
            goal_id=goal_id,
            minutes=minutes,
        )
    return minutes
