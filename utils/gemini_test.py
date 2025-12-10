import os
import json
import io

from flask import Flask, request, jsonify
import google.generativeai as genai
from dotenv import load_dotenv
from PIL import Image

# 1. INITIAL SETUP
# -----------------------------------------------------------------------------
# Load environment variables from the .env file
load_dotenv()

# Initialize the Flask application
app = Flask(__name__)

# Configure the Gemini API client
api_key = ""
if not api_key:
    raise ValueError("GEMINI_API_KEY not found. Please set it in your .env file.")
genai.configure(api_key=api_key)


# 2. DEFINE THE CORE PROMPT AND MODEL
# -----------------------------------------------------------------------------
# This detailed prompt guides Gemini to act as an expert appraiser.
EVALUATION_PROMPT = """
You are an expert agricultural equipment appraiser specializing in the Indian second-hand tractor market. Your task is to analyze the provided image(s) of a used tractor and generate a detailed evaluation report in a structured JSON format.
Please analyze the following aspects from the image(s):

1.  **Make and Model Identification:**
    *   Identify the brand (e.g., Mahindra, Swaraj, Massey Ferguson, Eicher).
    *   Identify the specific model or series if visible (e.g., Arjun, 275 DI, 485).

2.  **Attachment Analysis:**
    *   Detect the presence of a **Front Loader**. State clearly if it is present or absent.
    *   Detect the presence of a **Canopy/Sunshade**.
    *   Detect the presence of a **Front Bumper** and note if it is standard or custom.
    *   Mention any other visible attachments (e.g., backhoe, cultivator).

3.  **Condition Assessment:**
    *   **Tires:** Describe the condition of the front and rear tires (e.g., "Excellent, deep treads," "Fair, shows significant wear," "Poor, needs replacement").
    *   **Body and Paint:** Describe the cosmetic condition, noting any visible rust, dents, or paint fading. if rust is present, return the location of rust(e.g. "Rust on grille, front bumper")
    *   **Headlight:** Detect if the headlights are broken or not, the tractors with headlights in circular shape and outside the tractor body are usually old model nut the tractors with headlights inside the body are relativly new model. 
    *   **Overall Condition:** Give a summary rating (e.g., "Excellent," "Good," "Fair," "Poor").

4.  **Final Report Generation:**
    *   Synthesize all your findings into the JSON structure specified below.
    *   Do NOT include any text, explanations, or markdown formatting outside of the JSON object. Your entire response must be a single, valid JSON object.

**JSON Output Format:**
{
  "evaluation_summary": { "make": "string | null", "model": "string | null" },
  "attachments": { "has_front_loader": false, "has_canopy": true, "front_bumper_details": "string | null", "other_visible_attachments": ["string"] },
  "condition_assessment": { "overall_condition": "string", "tire_condition": "string", "body_and_paint_condition": "string" },
  "valuation_factors": { "positive": ["string"], "negative": ["string"] },
  "confidence_score": "float (0.0 to 1.0)"}
}
"""

# Initialize the Gemini model. 'gemini-1.5-flash' is fast and capable.
model = genai.GenerativeModel('gemini-2.5-flash-lite')


# 3. DEFINE THE API ENDPOINT
# -----------------------------------------------------------------------------
@app.route('/evaluate-tractor', methods=['POST'])
def evaluate_tractor():
    """API endpoint to evaluate a tractor image."""

    # --- Input Validation ---
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No file selected for uploading"}), 400

    if not file.mimetype.startswith('image/'):
        return jsonify({"error": "File is not an image"}), 415

    # --- Image Processing and Gemini API Call ---
    try:
        # Read image bytes and open with Pillow to verify it's a valid image
        image_bytes = file.read()
        img = Image.open(io.BytesIO(image_bytes))

        # Send the prompt and the image to the Gemini model
        response = model.generate_content([EVALUATION_PROMPT, img])

        # --- Response Cleaning and Parsing (CRITICAL STEP) ---
        # Gemini can sometimes wrap its JSON response in markdown. This removes it.
        response_text = response.text.strip().replace("```json", "").replace("```", "").strip()

        # Parse the cleaned text into a Python dictionary
        json_report = json.loads(response_text)

        # Return the successful JSON report
        return jsonify(json_report), 200

    except json.JSONDecodeError:
        # This error happens if the model's response is not valid JSON
        return jsonify({"error": "Failed to decode JSON from model response."}), 500
    except Exception as e:
        # Catch any other exceptions during the process
        return jsonify({"error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/')
def index():
    return "Tractor Evaluation API is running. Send a POST request with an image file to /evaluate-tractor."

# --- Run the Flask App ---
if __name__ == '__main__':
    app.run(debug=True,port=5455)