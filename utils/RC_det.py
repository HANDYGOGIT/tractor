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
from Vahan_payload import vahan_handler
from number_plate_utils import extract_number_plate,extract_number_plate_from_bytes



app = Flask(__name__)


GEMINI_API_KEY = ""
genai.configure(api_key=GEMINI_API_KEY)
# GEMINI_MODEL = "gemini-1.5-flash-latest" 
GEMINI_MODEL = genai.GenerativeModel('gemini-2.5-flash-lite')
openai.api_key = ""




@app.route("/classify_gemini", methods=["POST"])
def classify_gemini():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Read image directly from memory
    image_bytes = file.read()
    img = Image.open(io.BytesIO(image_bytes))

    prompt = "Classify this image strictly as one of: RC document, Toy, or others. Respond with just one label." \
    "Do not confuse visiting cards with RC documnets" 
    

    try:
        response = GEMINI_MODEL.generate_content([prompt, img])
        label = response.text.strip().lower()

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

        normalized_label = allowed_labels.get(label, "others")
        print(normalized_label)
        if normalized_label == 'RC document':
            file.seek(0)  
            image_bytes = file.read()
            rc_result = extract_number_plate_from_bytes([image_bytes])
            vahan_res=vahan_handler(rc_result[0]) 
            return jsonify({"classification": normalized_label, "number": rc_result,'vahan':vahan_res})



    except Exception as e:
        print(f"Gemini classification error: {e}")
        return jsonify({"error": "Failed to classify image"}), 500
    




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5291, debug=True)