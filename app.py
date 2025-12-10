import os
import uuid
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
import google.generativeai as genai
from PIL import Image
import io
from werkzeug.utils import secure_filename
from utils.tractor_evaluation_flow import evaluate_tractor_and_get_response_v2,get_or_create_thread
from utils.Vahan_payload import vahan_handler
from utils.user_intent_handler import handle_user_intent
from utils.s3_utils import upload_multiple_images_to_s3
from utils.db_logger_pg import save_tractor_data, get_tractor_data, create_tractor_valuation_table, save_user_activity, get_user_activity, get_user_activity_by_id
from utils.number_plate_utils import extract_number_plate_from_bytes
import base64

# -----------------------------------------------------------------------------------------------------
# for DB user activity
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

# pydantic class
class UserActivity(BaseModel):
    user_id: Optional[int]
    timestamp: Optional[datetime] = Field(default_factory=datetime.utcnow)
    utm_source: Optional[str]
    image_url: Optional[Dict]
    stage: Optional[str]
# -----------------------------------------------------------------------------------------------------

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

if not OPENAI_API_KEY or not ASSISTANT_ID:
    raise RuntimeError("Missing OPENAI_API_KEY or ASSISTANT_ID in .env file")

client = OpenAI(api_key=OPENAI_API_KEY)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
GEMINI_MODEL = genai.GenerativeModel('gemini-2.5-flash')

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB


UPLOAD_FOLDER = 'uploaded_images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize database table
create_tractor_valuation_table()

user_uploaded_images = {}


@app.route("/conversation", methods=["POST"])
def conversation():
    user_id = request.form.get("user_id")
    mobile = request.form.get("mobile", "")
    message = request.form.get("message")

    if not user_id or not message:
        return jsonify({"error": "Missing user_id or message"}), 400

    thread_id = get_or_create_thread(user_id, client)

    # Step 1: Check for existing valuation from database
    db_data = get_tractor_data(user_id)
    valuation = db_data['data_json'] if db_data else None
    if valuation:
        system_prompt = (
            "You are a friendly tractor valuation assistant. "
            "Your ONLY job is to answer user's queries based on the JSON valuation provided. "
            "If the user seems unhappy with the price or asks about resale doubts, reply politely:\n\n"
            "“Mujhe khed hai ki aapko humari valuation mein kuch kami lag rahi hai. "
            "Poora vishwaas rakhiye ki humne tractor ki condition dekh kar yeh value nikaali hai. "
            "Magar agar aapko fir bhi shanka hai to humne aapki request note kar li hai – "
            "aapko humare visheshagyo se call pe sahayata mil jaayegi.”\n\n"
            "Never answer anything that is not related to the valuation."
        )

        # Step 2: Post system + user message
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[
                {
                    "type": "text",
                    "text": (
                        f"SYSTEM:\n{system_prompt}\n\n"
                        f"VALAUTION DATA:\n{json.dumps(valuation, ensure_ascii=False)}\n\n"
                        f"USER MESSAGE:\n{message}"
                    ),
                }
            ],
        )

        # Step 3: Run assistant (NO tool calling)
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            tool_choice="none"
        )

        # Step 4: Poll for completion
        import time
        for _ in range(10):
            time.sleep(1)
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                return jsonify({"error": "Assistant run failed"}), 500
        else:
            return jsonify({"error": "Assistant timeout"}), 500

        # Step 5: Get reply
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        reply = ""
        if messages.data:
            for content in messages.data[0].content:
                if content.type == "text":
                    reply += content.text.value

        return jsonify({
            "mobile": mobile,
            "user_id": user_id,
            "reply": reply
        })

    else:
        # No valuation yet — guide user to start
        return jsonify({
            "mobile": mobile,
            "user_id": user_id,
            "reply": "Abhi tak valuation nahi hua hai. Kripya tractor ki photo bhejiye, main madad karta hoon 📸"
        }), 200


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

        response = client.responses.create(
            model="gpt-4.1",  # or gpt-4o if you prefer
            input=[
                {
                    "role": "system",
                    "content": (
    "You are a strict image classifier. "
    "Classify the image as one of: 'tractor', 'RC document', 'Toy', or 'others'. "
    "If it is a tractor, also determine whether it is a real-life outdoor photo or a fake/product/render/screen photo. "
    "Cues for real photo: outdoor environment, natural background, lighting, sky, soil, or people nearby. "
    "Cues for fake or artificial photo: plain white background, product studio lighting, toy look, digital render, "
    "or a photo taken of a computer/laptop/phone screen. "
    "Respond ONLY in valid JSON format as: "
    '{"classification": "<tractor|RC document|Toy|others>", "is_real_photo": <true|false|null>}.'
)},
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
        raw_text = response.output_text.strip()
        raw_text=json.loads(raw_text)
        print(raw_text)

        raw_label = raw_text['classification'].lower()
        is_real = raw_text['is_real_photo']
        return allowed_labels.get(raw_label, "others"),is_real

    except Exception as e:
        print(f"Error classifying image: {e}")
        return "error"


@app.route("/classify_image", methods=["POST"])
def classify():
    if 'image' not in request.files:
        return jsonify({"error": "No image file found in form-data"}), 400

    image_file = request.files['image']
    label,is_real_flag = classify_image_type_fast(image_file)
    if(is_real_flag==False):
        return jsonify({"classification": label,"Is_real_flag":is_real_flag,"message":"Maaf kijie, magar ye tasveer mujhe asli nahi lag rhi ye shayad screenshot, internet se downloaded ya kisi screen se kheechi hui image lag rhi hai. Kripya tractor ki asli tasveer hi bheje"})

    return jsonify({"classification": label,"Is_real_flag":is_real_flag})

# @app.route("/classify_image", methods=["POST"])
# def classify_gemini():
#     if 'image' not in request.files:
#         return jsonify({"error": "No image uploaded"}), 400

#     file = request.files['image']
#     if file.filename == '':
#         return jsonify({"error": "No file selected"}), 400

#     # Read image directly from memory
#     image_bytes = file.read()
#     img = Image.open(io.BytesIO(image_bytes))

#     prompt = '''You are a strict image classifier. 
#     Classify the image as one of: 'tractor', 'RC document', 'Toy', or 'others'. 
#     If it is a tractor, also determine whether it is a real-life outdoor photo or a fake/product/render/screen photo. 
#     Cues for real photo: outdoor environment, natural background, lighting, sky, soil, or people nearby. 
#     Cues for fake or artificial photo: plain white background, product studio lighting, toy look, digital render, 
#     or a photo taken of a computer/laptop/phone screen. 
#     Respond ONLY in valid JSON format as: 
#     {"classification": "<tractor|RC document|Toy|others>", "is_real_photo": <true|false|null>}.'''
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


# @app.route("/classify_rc", methods=["POST"])
# def classify_rc():
#     if 'image' not in request.files:
#         return jsonify({"error": "No image uploaded"}), 400

#     file = request.files['image']
#     if file.filename == '':
#         return jsonify({"error": "No file selected"}), 400

#     # Read image directly from memory
#     image_bytes = file.read()
#     img = Image.open(io.BytesIO(image_bytes))

#     prompt = "Classify this image strictly as one of: RC document, Toy, or others. Respond with just one label." \
#     "Do not confuse visiting cards with RC documnets" 
    

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
#         print(normalized_label)
#         if normalized_label == 'RC document':
#             file.seek(0)  
#             image_bytes = file.read()
#             rc_result = extract_number_plate_from_bytes([image_bytes])
#             vahan_res=vahan_handler(rc_result[0]) 
#             return jsonify({"classification": normalized_label, "number": rc_result,'vahan':vahan_res})



#     except Exception as e:
#         print(f"Gemini classification error: {e}")
#         return jsonify({"error": "Failed to classify image"}), 500



GEMINI_URL = f"https://aiplatform.googleapis.com/v1/publishers/google/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}"


@app.route("/classify_rc", methods=["POST"])
def classify_rc():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    # Read image bytes
    image_bytes = file.read()

    # Convert to Base64
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    prompt = (
        "Classify this image strictly as one of: RC document, Toy, or others. "
        "Respond with exactly one label. Do not confuse visiting cards with RC documents."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": b64_image
                        }
                    },
                    {
                        "text": prompt
                    }
                ]
            }
        ]
    }

    try:
        # Call Gemini 2.5 Flash-Lite
        response = requests.post(GEMINI_URL, json=payload)
        result = response.json()

        # Extract output text
        label = (
            result.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
            .strip()
            .lower()
        )

        # Allowed mappings
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
        print("Model Output:", label)
        print("Normalized:", normalized_label)

        # If it's RC, extract number + fetch vahan
        if normalized_label == 'RC document':
            file.seek(0)
            image_bytes = file.read()
            rc_result = extract_number_plate_from_bytes([image_bytes])
            vahan_res = vahan_handler(rc_result[0])

            return jsonify({
                "classification": normalized_label,
                "number": rc_result,
                "vahan": vahan_res
            })

        return jsonify({"classification": normalized_label})

    except Exception as e:
        print(f"Gemini classification error: {e}")
        return jsonify({"error": "Failed to classify image"}), 500




@app.route("/chat", methods=["POST"])
def chat():
    # Handle JSON data instead of form data
    if request.is_json:
        data = request.get_json()
        mobile = data.get("mobile", "")
        user_id = data.get("user_id", mobile if mobile else "default_user")
        image_urls = data.get("image_urls", [])
        rc_url = data.get("rc_url", "")
        location = data.get("location", "")
        vahan_data = data.get("vahan", {})

    # Combine all URLs (images + RC)
    all_urls = image_urls.copy()
    if rc_url:
        all_urls.append(rc_url)

    if not all_urls:
        return jsonify({"error": "No images or RC URL provided"}), 400

    print(f"[INFO] Processing {len(all_urls)} images for user {user_id}")
    print(f"[INFO] Image URLs: {image_urls}")
    print(f"[INFO] RC URL: {rc_url}")
    print(f"[INFO] Vahan Data: {vahan_data}")

    # Evaluate images using URLs directly
    try:
        # pass rc details here if available from rc photos
        reply, eval_data = evaluate_tractor_and_get_response_v2(user_id, all_urls, client, ASSISTANT_ID, vahan_data)  
        
        # Add mobile, user_id, reply, and image URLs to evaluation data
        eval_data['mobile'] = mobile
        eval_data['user_id'] = user_id
        eval_data['reply'] = reply
        eval_data['image_urls'] = image_urls
        eval_data['rc_url'] = rc_url
        eval_data['location'] = location

        # Save to database with enhanced data
        save_tractor_data(user_id, eval_data, image_urls)
        
        return jsonify({
            "mobile": mobile,
            "user_id": user_id,
            "reply": reply,
            "valuation_result": eval_data.get("valuation_result", {}),
            "image_urls": image_urls,
            "rc_url": rc_url,
            "debug": eval_data  # Optional: remove this line in production
        })
    except Exception as e:
        print(f"[ERROR] Failed to evaluate images: {e}")
        return jsonify({"error": str(e)}), 500





@app.route("/upload_s3", methods=["POST"])
def upload_to_s3():
    """
    Upload images directly to S3 and return URLs
    Simple endpoint that accepts multiple images via form data
    """
    user_id = request.form.get("user_id", "default_user")
    image_files = request.files.getlist("images")

    if not image_files:
        return jsonify({"error": "No images provided"}), 400

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    saved_image_paths = []

    # Process uploaded files
    for file in image_files:
        if file.filename == '':
            continue
        # Generate unique UUID and prepend to filename
        unique_id = str(uuid.uuid4())
        original_filename = secure_filename(file.filename)
        filename = f"{unique_id}_{original_filename}"
        path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(path)
        saved_image_paths.append(path)

    # Upload images to S3
    image_urls = []
    if saved_image_paths:
        print(f"[INFO] Uploading {len(saved_image_paths)} images to S3 for user {user_id}")
        image_urls = upload_multiple_images_to_s3(saved_image_paths, user_id)
        print(f"[INFO] Successfully uploaded {len(image_urls)} images to S3")
        
        # Clean up local files after upload
        for path in saved_image_paths:
            try:
                os.remove(path)
            except Exception as e:
                print(f"[WARNING] Failed to delete local file {path}: {e}")

    return jsonify({
        "user_id": user_id,
        "uploaded_count": len(image_urls),
        "image_urls": image_urls,
        "message": f"Successfully uploaded {len(image_urls)} images to S3"
    })




# DB user-activity endpoint--------------------------------------------------------
@app.route("/user-activity", methods=["POST"])
def create_or_update_user():
    try:
        data = request.get_json()
 
        user_id = data.get("user_id")
        created_at = data.get("created_at", datetime.utcnow()) 
        utm_source = data.get("utm_source")
        image_url = data.get("image_url")
        stage = data.get("stage")
 
        saved_user_id = save_user_activity(
        user_id=user_id,
        utm_source=utm_source,
        image_url=image_url,
        stage=stage
    )
 
        if not saved_user_id:
            return jsonify({"error": "Failed to save user activity"}), 500
 
        return jsonify({"message": "Record saved successfully", "user_id": saved_user_id}), 200
 
    except Exception as e:
        print(f"[ERROR - create_or_update_user]: {e}")
        return jsonify({"error": str(e)}), 500



@app.route("/get-all-user-activity", methods=["GET"])
def get_all_user_activity():
    """
    Get all user activity data from the database
    Optional query parameters:
    - start_date: Filter records from this date (format: YYYY-MM-DD)
    - end_date: Filter records up to this date (format: YYYY-MM-DD)
    
    Also supports JSON payload:
    {
        "start_date": "2025-11-18",
        "end_date": "2025-11-18"
    }
    """
    try:
        # Get date filters from query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Also support JSON body for date filters (if sent in payload)
        try:
            if request.data and request.is_json:
                data = request.get_json(silent=True)
                if data:
                    start_date = data.get('start_date') or start_date
                    end_date = data.get('end_date') or end_date
        except Exception as json_error:
            print(f"[WARNING - JSON parsing]: {json_error}")
            # Continue with query parameters if JSON parsing fails
        
        # Get filtered data from database (filters by created_at field)
        user_activity_data = get_user_activity(start_date=start_date, end_date=end_date)
        
        response_msg = "User activity data retrieved successfully"
        if start_date or end_date:
            response_msg += f" (filtered by created_at: {start_date or 'any'} to {end_date or 'any'})"
        
        return jsonify({
            "message": response_msg,
            "count": len(user_activity_data),
            "filters": {
                "start_date": start_date,
                "end_date": end_date
            },
            "data": user_activity_data
        }), 200
        
    except Exception as e:
        print(f"[ERROR - get_all_user_activity]: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/user-activity/<user_id>", methods=["GET"])
def get_user_activity_by_user_id(user_id):
    """
    Get user activity data for a specific user
    """
    try:
        user_activity_data = get_user_activity_by_id(user_id)
        
        if not user_activity_data:
            return jsonify({"error": "User activity not found"}), 404
        
        return jsonify({
            "message": "User activity data retrieved successfully",
            "data": user_activity_data
        }), 200
        
    except Exception as e:
        print(f"[ERROR - get_user_activity_by_user_id]: {e}")
        return jsonify({"error": str(e)}), 500



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5201, debug=True, threaded=True)



# @app.route("/conversation", methods=["POST"])
# def conversation():
#     user_id = request.form.get("user_id", "default_user")
#     user_input = request.form.get("text_input", "").strip()
#     thread_id = get_or_create_thread(user_id, client)

#     # Load valuation store
#     # valuation_store_path = "uploaded_images/user_valuations.json"
#     # if os.path.exists(valuation_store_path):
#     #     with open(valuation_store_path, "r", encoding="utf-8") as f:
#     #         valuation_store = json.load(f)
#     # else:
#     #     valuation_store = {}

#     user_eval = valuation_store.get(user_id)

#     # if user_input:
#     #     # Language adaptive prompt
#     lang_instruction = (
#             "Please respond in the same language and tone as the user's message. "
#             "If the message is in Hindi or Hinglish, reply in that language. "
#             "If it's in English, use English."
#         )
#     #     content = f"{lang_instruction}\n\nUser: {user_input}"
#     # elif user_eval and user_eval.get("valuation_result"):
#     #     content = (
#     #         "We have already completed your tractor valuation. Here's the result:\n"
#     #         + json.dumps(user_eval["valuation_result"], indent=2, ensure_ascii=False)
#     #     )
#     # else:
#     #     content = "Please upload images of your tractor to begin the resale evaluation."

#     if user_input and user_eval and user_eval.get("valuation_result"):
#         content = (
#             f"{lang_instruction}\n\n"
#             "User previously completed a tractor valuation. Here is the result:\n"
#             + json.dumps(user_eval["valuation_result"], indent=2, ensure_ascii=False)
#             + f"\n\nNow user says: {user_input}\nPlease respond naturally."
#                 )
#     elif user_input:
#         content = f"{lang_instruction}\n\nUser: {user_input}"
#     elif user_eval and user_eval.get("valuation_result"):
#         content = (
#             "We have already completed your tractor valuation. Here's the result:\n"
#             + json.dumps(user_eval["valuation_result"], indent=2, ensure_ascii=False)
#         )
#     else:
#         content = "Please upload images of your tractor to begin the resale evaluation."


#     # Post user message
#     client.beta.threads.messages.create(
#         thread_id=thread_id,
#         role="user",
#         content=[{"type": "text", "text": content}]
#     )

#     run = client.beta.threads.runs.create(
#         assistant_id=ASSISTANT_ID,
#         thread_id=thread_id,
#         tool_choice="none"
#     )

#     import time
#     retry = 0
#     while retry < 10:
#         time.sleep(1)
#         run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
#         if run.status == "completed":
#             break
#         elif run.status == "failed":
#             return jsonify({"error": "Assistant run failed"}), 500
#         retry += 1

#     # Fetch reply
#     messages = client.beta.threads.messages.list(thread_id=thread_id)
#     latest = messages.data[0]
#     reply = ""
#     for content in latest.content:
#         if content.type == "text":
#             reply += content.text.value

#     return jsonify({"reply": reply})
# @app.route("/conversation", methods=["POST"])
# def conversation():
#     user_id = request.form.get("user_id")
#     user_message = request.form.get("message")

#     thread_id = get_or_create_thread(user_id, client)

#     # Add message to thread
#     client.beta.threads.messages.create(
#         thread_id=thread_id,
#         role="user",
#         content=user_message
#     )

#     # Start assistant run with tool_choice = auto
#     run = client.beta.threads.runs.create(
#         assistant_id=ASSISTANT_ID,
#         thread_id=thread_id,
#         tool_choice="auto"
#     )

#     # Poll and respond to tool calls
#     retry = 0
#     while retry < 10:
#         import time
#         time.sleep(1)
#         run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

#         if run.status == "requires_action":
#             tool_calls = run.required_action.submit_tool_outputs.tool_calls
#             responses = []

#             for tool in tool_calls:
    #             if tool.function.name == "handle_user_intent":
    #                 args = json.loads(tool.function.arguments)
    #                 intent = args.get("intent")
    #                 rc_number = args.get("rc_number")

    #                 if intent == "start_evaluation":
    #                     responses.append("Aap apne tractor ki photo bhejiye, valuation ke liye. 📸")
    #                 elif intent == "valuation_question":
    #                     valuation = valuation_store.get(user_id)
    #                     if valuation:
    #                         responses.append("Aapka tractor valuation pahle ho chuka hai. Agar detail chahiye toh batayein.")
    #                     else:
    #                         responses.append("Abhi tak valuation nahi hua hai. Kripya photo bhejiye.")
    #                 elif intent == "revaluation_requested":
    #                     responses.append("Thik hai. Naye images bhejiye, main dobara valuation kar dunga.")
    #                 elif intent == "rc_number_provided" and rc_number:
    #                     try:
    #                         data = vahan_handler(rc_number)
    #                         valuation_store[user_id] = {"vahan_data": data}
    #                         responses.append(f"RC data mil gaya ✅:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
    #                     except Exception as e:
    #                         responses.append("RC number process nahi ho paya. Dubara koshish karein.")
    #                 elif intent == "off_topic":
    #                     responses.append("Main sirf tractor valuation mein madad karta hoon 🙏")
    #                 elif intent == "greeting":
    #                     responses.append("Namaste! Main aapki tractor valuation mein madad karta hoon. 📋")

    #         # Return response to client
    #         return jsonify({
    #             "reply": "\n\n".join(responses)
    #         })

    #     elif run.status == "completed":
    #         # Fall back to assistant reply
    #         messages = client.beta.threads.messages.list(thread_id=thread_id)
    #         reply = ""
    #         for content in messages.data[0].content:
    #             if content.type == "text":
    #                 reply += content.text.value
    #         return jsonify({"reply": reply})

    #     elif run.status == "failed":
    #         return jsonify({"error": "Assistant run failed"}), 500

    #     retry += 1

    # return jsonify({"error": "Assistant timeout"}), 500

# @app.route("/conversation", methods=["POST"])
# def conversation():
#     import time
#     user_id = request.form.get("user_id", "default_user")
#     user_message = request.form.get("message")

#     if not user_message:
#         return jsonify({"error": "No message provided"}), 400

#     # Step 1: Get or create thread
#     thread_id = get_or_create_thread(user_id, client)

#     # Step 2: Wait until thread is free (or cancel stuck run)
#     def wait_until_thread_is_free(client, thread_id, max_wait=15):
#         runs = client.beta.threads.runs.list(thread_id=thread_id).data
#         for run in runs:
#             if run.status in ["queued", "in_progress", "requires_action"]:
#                 run_id = run.id
#                 for _ in range(max_wait):
#                     time.sleep(1)
#                     current = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
#                     if current.status in ["completed", "failed", "cancelled", "expired"]:
#                         return
#                 # Cancel stuck run
#                 try:
#                     client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run_id)
#                     print(f"[INFO] Cancelled stuck run: {run_id}")
#                 except Exception as e:
#                     print(f"[ERROR] Failed to cancel run {run_id}: {e}")
#                 raise Exception(f"Run {run_id} on thread {thread_id} is stuck. Cancelled after timeout.")

#     wait_until_thread_is_free(client, thread_id)

#     # Step 3: Add user message
#     client.beta.threads.messages.create(
#         thread_id=thread_id,
#         role="user",
#         content=user_message
#     )

#     # Step 4: Start new assistant run
#     run = client.beta.threads.runs.create(
#         assistant_id=ASSISTANT_ID,
#         thread_id=thread_id,
#         tool_choice="auto"
#     )

#     # Step 5: Poll run status
#     for _ in range(20):
#         time.sleep(1)
#         run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

#         if run.status == "requires_action":
#             tool_calls = run.required_action.submit_tool_outputs.tool_calls
#             tool_outputs = []

#             for tool_call in tool_calls:
#                 func_name = tool_call.function.name
#                 args = json.loads(tool_call.function.arguments)

#                 if func_name == "handle_user_intent":
#                     output = handle_user_intent(user_id=user_id, valuation_store=valuation_store, **args)
#                     tool_outputs.append({
#                         "tool_call_id": tool_call.id,
#                         "output": json.dumps(output)
#                     })

#             # Submit tool outputs
#             client.beta.threads.runs.submit_tool_outputs(
#                 thread_id=thread_id,
#                 run_id=run.id,
#                 tool_outputs=tool_outputs
#             )

#         elif run.status == "completed":
#             break
#         elif run.status in ["failed", "cancelled"]:
#             return jsonify({"error": f"Run failed with status: {run.status}"}), 500

#     # Step 6: Get final assistant message
#     messages = client.beta.threads.messages.list(thread_id=thread_id).data
#     latest = messages[0] if messages else None
#     if not latest:
#         return jsonify({"error": "No reply from assistant"}), 500

#     reply_text = ""
#     for part in latest.content:
#         if part.type == "text":
#             reply_text += part.text.value

#     return jsonify({"reply": reply_text})
