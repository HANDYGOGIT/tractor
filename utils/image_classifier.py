# utils/image_classifier.py

import os
import time
import json
import re
import logging
from openai import OpenAI
import openai
import base64
from typing import List, Tuple
import os
import shutil
from flask import Flask, request, jsonify
import requests
import os
import google.generativeai as genai
from PIL import Image
import io



app = Flask(__name__)


GEMINI_API_KEY = ""
genai.configure(api_key=GEMINI_API_KEY)
# GEMINI_MODEL = "gemini-1.5-flash-latest" 
GEMINI_MODEL = genai.GenerativeModel('gemini-2.0-flash-lite')
OPENAI_API_KEY = ""

client_resp = OpenAI(api_key=OPENAI_API_KEY)
def encode_image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def encode_url_to_base64(url: str) -> str:
    """Download image from URL and convert to base64"""
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode()
        else:
            raise Exception(f"Failed to download image: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error downloading image from {url}: {e}")
        raise

def classify_image_type_bulk(image_paths: List[str]) -> List[Tuple[str, str]]:
    """
    Classify each image as 'tractor', 'RC document','Toy','cartoon','animated drawing sketch' or 'others' using GPT-4 Vision.
    Can handle both local file paths and URLs.
    Response is strictly one of the 6 values.
    """
    allowed_labels = {
        'tractor': 'tractor',
        'rc': 'RC document',
        'rc document': 'RC document',
        'registration certificate': 'RC document',
        'toy':'Toy',
        'toys':'Toy',
        'cartoon':'Toy',
        'animated drawing sketch':'Toy',
        'others': 'others',
        'other': 'others'
    }
    base_dir='./classified_images'
    folder_map = {
        "tractor": os.path.join(base_dir, "tractor"),
        "RC document": os.path.join(base_dir, "rc"),
        "others": os.path.join(base_dir, "others"),
        "Toy": os.path.join(base_dir, "Toy")
    }
    for folder in folder_map.values():
        if os.path.exists(folder):
            shutil.rmtree(folder)
        os.makedirs(folder, exist_ok=True)

    results = []
    
    for i, path_or_url in enumerate(image_paths):
        # Check if it's a URL or local path
        is_url = path_or_url.startswith(('http://', 'https://'))
        
        try:
            if is_url:
                # Handle URL
                image_b64 = encode_url_to_base64(path_or_url)
                filename = f"url_image_{i}.jpg"  # Generate filename for URL
            else:
                # Handle local path
                image_b64 = encode_image_to_base64(path_or_url)
                filename = os.path.basename(path_or_url)

            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a strict image classifier. "
                            "Given an image, you must respond with exactly one of the following labels: "
                            "'tractor', 'RC document','Toy' or 'others'. Respond with just one of these labels only. "
                            "Do not include any explanation."
                        )
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Classify this image strictly as: tractor, RC document, or others."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            },
                        ]
                    }
                ],
                max_tokens=10,
            )

            raw_label = response.choices[0].message.content.strip().lower()
            label = allowed_labels.get(raw_label, "others")
            results.append((filename, label))

            # Only move files if they are local paths
            if not is_url:
                dest_folder = folder_map[label]
                shutil.move(path_or_url, os.path.join(dest_folder, filename))

        except Exception as e:
            print(f"Error processing {path_or_url}: {e}")
            filename = f"error_image_{i}.jpg" if is_url else os.path.basename(path_or_url)
            results.append((filename, "error"))

    return results

@app.route("/", methods=["GET"])
def test_health_classification():
    return jsonify({"reply": "classification_API running"})

def classify_image_type_fast(image_file):
    """
    Classify an uploaded image (FileStorage) as 'tractor', 'RC document', 'Toy', or 'others' using the Responses API.
    Returns the normalized classification label as a string.
    """
    allowed_labels = {
        'tractor': 'tractor',
        'rc': 'RC document',
        'rc document': 'RC document',
        'registration certificate': 'RC document',
        'toy': 'Toy',
        'toys': 'Toy',
        'cartoon': 'Toy',
        'animated drawing sketch': 'Toy',
        'others': 'others',
        'other': 'others'
    }

    try:
        # Read the image and encode as base64 → data URL
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{image_b64}"

        response = client_resp.responses.create(
            model="gpt-4.1",  # or gpt-4o if you prefer
            input=[
                {
                    "role": "system",
                    "content": "You are a strict image classifier. Reply with exactly one of: 'tractor', 'RC document', 'Toy', or 'others'. No explanation."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Classify this image."},
                        {"type": "input_image", "image_url": image_data_url}
                    ]
                }
            ],
            max_output_tokens=16,
        )

        raw_label = response.output_text.strip().lower()
        return allowed_labels.get(raw_label, "others")

    except Exception as e:
        print(f"Error classifying image: {e}")
        return "error"


@app.route("/classification", methods=["POST"])
def classify():
    if 'image' not in request.files:
        return jsonify({"error": "No image file found in form-data"}), 400

    image_file = request.files['image']
    label = classify_image_type_fast(image_file)
    return jsonify({"classification": label})

# image_paths = [r"C:\Users\behta\Downloads\tractor_img\275-di-sp-plus-202872-1750306884-3.jpg", r"C:\Users\behta\Downloads\tractor_img\275-di-sp-plus-202872-1750306873-0.jpg",r"C:\Users\behta\Downloads\tractor_img\275-di-sp-plus-202872-1750306877-1.jpg"]
# print(classify_image_type_bulk(image_paths))


# @app.route("/classify_gemini", methods=["POST"])
# def classify_gemini():
#     if 'image' not in request.files:
#         return jsonify({"error": "No image uploaded"}), 400

#     file = request.files['image']
#     if file.filename == '':
#         return jsonify({"error": "No file selected"}), 400

#     # Read image directly from memory
#     image_bytes = file.read()
#     img = Image.open(io.BytesIO(image_bytes))

#     prompt = "Classify this image strictly as one of: tractor, RC document, Toy, or others. Respond with just one label."
#     try:
#         response = GEMINI_MODEL.generate_content([prompt, img])
#         label = response.text.strip().lower()

#         allowed_labels = {
#             'tractor': 'tractor',
#             'rc': 'RC document',
#             'rc document': 'RC document',
#             'registration certificate': 'RC document',
#             'toy': 'Toy',
#             'toys': 'Toy',
#             'cartoon': 'Toy',
#             'animated drawing sketch': 'Toy',
#             'others': 'others',
#             'other': 'others'
#         }

#         normalized_label = allowed_labels.get(label, "others")
#         return jsonify({"classification": normalized_label})

#     except Exception as e:
#         print(f"Gemini classification error: {e}")
#         return jsonify({"error": "Failed to classify image"}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5299, debug=True)
