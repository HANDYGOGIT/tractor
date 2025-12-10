# utils/top_price.py
import json
from rapidfuzz import fuzz, process
import os

json_path = os.path.join(os.path.dirname(__file__), "new_tractor_data1.json")

with open(json_path, "r", encoding="utf-8") as f:
    tractors = json.load(f)

def get_max_price_nearest_tractor(brand, model):
    input_title = f"{brand} {model}".lower()
    titles = [t["title"].lower() for t in tractors]
    match, score, idx = process.extractOne(input_title, titles, scorer=fuzz.token_sort_ratio)
    matched_tractor = tractors[idx]

    return {
        "matched_title": matched_tractor["title"],
        "match_score": score,
        "max_price": matched_tractor["price_max"]
    }
