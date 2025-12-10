import os
import time
import base64
import re
from flask import Flask, request, jsonify
from openai import OpenAI
from dotenv import load_dotenv
from utils.Vahan_payload import vahan_handler
from utils.number_plate_utils import extract_number_plate
from utils.brand_model_utils import predict_brand_model
from utils.rust_tire_utilsV2 import analyze_rust_tire
from utils.top_price_utils import get_max_price_nearest_tractor
from utils.depreciation_func import evaluate_full_tractor_analysis
from tool_call_handler import handle_tool_calls
import json
import time
from openai import OpenAI
from werkzeug.utils import secure_filename
import os
from flask_cors import CORS
import uuid
import requests

load_dotenv()

app = Flask(__name__)

# CORS(app, support_credentials=True)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

user_threads = {}
user_uploaded_images = {} 
def get_or_create_thread(user_id):
    if user_id in user_threads:
        return user_threads[user_id]
    thread = client.beta.threads.create()
    user_threads[user_id] = thread.id
    return thread.id

def encode_image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")







client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("ASSISTANT_ID")


def encode_image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def run_tool(thread_id, tool_name, tool_inputs):
    run = client.beta.threads.runs.create(
        assistant_id=ASSISTANT_ID,
        thread_id=thread_id,
        tool_choice={"type": "function", "function": {"name": tool_name}},
        additional_instructions=json.dumps(tool_inputs)
    )
    while True:
        status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if status.status == "completed":
            break
        elif status.status == "failed":
            raise Exception(f"{tool_name} tool failed")
        time.sleep(1)

    messages = client.beta.threads.messages.list(thread_id=thread_id).data
    for message in messages:
        for content in message.content:
            if content.type == "text":
                return content.text.value
    return "{}"


def run_full_evaluation(image_paths):
    thread = client.beta.threads.create()


    tractor_imgs = [p for p in image_paths if 'rc' not in p.lower()]
    rc_imgs = [p for p in image_paths if 'rc' in p.lower()]

    rc_base64 = encode_image_to_base64(rc_imgs[0]) if rc_imgs else encode_image_to_base64(tractor_imgs[0])
    tractor_base64s = [encode_image_to_base64(p) for p in tractor_imgs]

    #Extract RC Number
    rc_number = ""
    try:
        np_response = run_tool(thread.id, "extract_number_plate", {"image_base64": rc_base64})
        rc_number = re.sub(r"\D", "", np_response)
    except Exception:
        rc_number = ""

    #Call Vahan API
    vahan_data = {}
    if rc_number:
        try:
            vahan_json = run_tool(thread.id, "vahan_handler", {"rc_number": rc_number})
            vahan_data = json.loads(vahan_json)
        except Exception:
            vahan_data = {}

    #Brand/Model Prediction
    brand_model = {}
    try:
        bm_json = run_tool(thread.id, "predict_brand_model", {"images_base64": tractor_base64s})
        brand_model = json.loads(bm_json)
    except Exception:
        brand_model = {}

    #Rust/Tire Analysis
    rust_data = {}
    try:
        rust_json = run_tool(thread.id, "analyze_rust_tire", {"images_base64": tractor_base64s})
        rust_data = json.loads(rust_json)
    except Exception:
        rust_data = {}

    #Top Price Lookup
    brand = vahan_data.get("brand") or brand_model.get("brand", "")
    model = vahan_data.get("model") or brand_model.get("model", "")
    top_price = {}
    try:
        price_json = run_tool(thread.id, "get_max_price_nearest_tractor", {"brand": brand, "model": model})
        top_price = json.loads(price_json)
    except Exception:
        top_price = {}

    #Final Valuation
    age = int(vahan_data.get("age", 5))
    final_input = {
        "brand_model_prediction": {"brand": brand, "model": model},
        "rust_tire_analysis": rust_data,
        "top_price_fuzzy_match": top_price,
        "age_years": age
    }

    try:
        final_reply = run_tool(thread.id, "evaluate_full_tractor_analysis", final_input)
        return final_reply
    except Exception:
        return "Sorry, I couldn’t generate a proper valuation at the moment."







UPLOAD_FOLDER = 'uploaded_images'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/", methods=["GET"])
def check_run():
    return jsonify({
        "reply": "Server up and running"
    })


@app.route("/chat", methods=["POST"])
def chat_with_assistant():
    from werkzeug.utils import secure_filename
    global user_uploaded_images

    user_id = request.form.get("user_id", "default_user")
    user_message = request.form.get("message", "").strip()
    image_files = request.files.getlist("images")
    source = request.form.get("source", "web").lower()

    if not user_message and "images" not in request.files and "images" not in request.form:
        return jsonify({"error": "Either message or image is required"}), 400
    if user_id not in user_uploaded_images:
        user_uploaded_images[user_id] = []
    #  Step 1: Reuse or create thread
    thread_id = get_or_create_thread(user_id)

    #  Step 2: Upload images to OpenAI
    uploaded_image_ids = []
    # uploaded_image_paths=[]
    if source == "web":
        if image_files:
            os.makedirs("uploaded_images", exist_ok=True)
            # os.makedirs("uploaded_images_"+user_id, exist_ok=True)
            for file in image_files:
                filename = secure_filename(file.filename)
                save_path = os.path.join("uploaded_images", filename)
                file.save(save_path)
                # uploaded_image_paths.append(save_path)
                user_uploaded_images[user_id].append(save_path)

                with open(save_path, "rb") as f:
                    uploaded = client.files.create(file=f, purpose="vision")
                    uploaded_image_ids.append(uploaded.id)
    elif source == "whatsapp":
        image_urls = request.form.getlist("images")
        for url in image_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    filename = f"{user_id}-{uuid.uuid4().hex}.jpg"
                    save_path = os.path.join(UPLOAD_FOLDER, filename)
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                    user_uploaded_images[user_id].append(save_path)

                    with open(save_path, "rb") as f:
                        uploaded = client.files.create(file=f, purpose="vision")
                        uploaded_image_ids.append(uploaded.id)
            except Exception as e:
                print(f"[ERROR] Failed to download WhatsApp image: {e}")

    #  Step 3: Prepare assistant message
    message_content = []
    if user_message:
        message_content.append({"type": "text", "text": user_message})
    for file_id in uploaded_image_ids:
        message_content.append({
            "type": "image_file",
            "image_file": {"file_id": file_id}
        })

    #  Step 4: Post message
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role="user",
        content=message_content
    )

    #  Step 5: Run the assistant
    run = client.beta.threads.runs.create(
        assistant_id=ASSISTANT_ID,
        thread_id=thread_id
    )

    #  Step 6: Handle tool calls or wait for completion
    while True:
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)

        if run.status == "requires_action":
            uploaded_image_paths = user_uploaded_images.get(user_id, [])
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            handle_tool_calls(client, thread_id, run, tool_calls,uploaded_image_paths)

        elif run.status == "completed":
            break
        elif run.status == "failed":
            return jsonify({"error": "Assistant run failed"}), 500

        time.sleep(1)

    #  Step 7: Get assistant reply
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    latest = messages.data[0]

    full_reply = ""
    for content in latest.content:
        if content.type == "text":
            full_reply += content.text.value

    return jsonify({
        "reply": full_reply
    })






if __name__ == "__main__":
    # app.run(debug=True)
    app.run(host="0.0.0.0", port=5201, debug=True,threaded=True)