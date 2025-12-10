import os
import uuid
import requests
import json
from openai import OpenAI
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
from utils.tractor_evaluation_flow import evaluate_tractor_and_get_response_v2,get_or_create_thread
import time
from utils.user_intent_handler import handle_user_intent
import threading
from utils.db_logger_pg import log_message, save_tractor_data
from waitress import serve 
import random
from utils.choose_static import speak

# =========================
# Humanized message pools
# =========================
# MESSAGES = {
#     "wait": [
#         "Aapka message process ho raha hai. Kripya kuch der ruk jaiye.",
#         "Main abhi aapke message par kaam kar raha hoon. Thodi der dein.",
#         "Request receive ho gayi hai, processing chal rahi hai. Bas thoda sa time.",
#         "Note kar liya hai—processing mein hai. Kripya thoda sa intazaar karein."
#     ],
#     "busy_processing": [
#         "Pehle wala message abhi process ho raha hai. Kripya thoda intazaar karen.",
#         "Abhi ek request chal rahi hai. Jaisi hi khatam hogi, aapka agla message le lunga.",
#         "System aapke last message par kaam kar raha hai. Naya message bhejne se phle kuch deer intezaare kre."
#     ],
#     "media_processing_error": [
#         "Media process karte waqt dikkat aayi. Aap dobara koshish karen, main madad karta hoon.",
#         "Image ko process karte hue error aaya. Kripya ek baar dubara bhej dijiye.",
#         "Maaf kijiye, photo par kaam karte waqt issue aaya. Aap phir se bhej sakte hain?"
#     ],
#     "conversation_error": [
#         "Reply tayar karte waqt dikkat aayi. Aap apna message dobara bhej sakte hain?",
#         "System ko reply generate karne mein problem hui. Kripya dobara try karein.",
#         "Thoda issue aa gaya. Aapka message dubara share kar denge?"
#     ],
#     "assistant_timeout": [
#         "Reply aane mein zyada time lag raha hai. Main phir se try kar raha hoon.",
#         "System response slow hai. Kripya thodi der baad dobara koshish karein.",
#         "Lagta hai response me der ho rahi hai. Aap thoda intazaar karein ya phir se bhejein."
#     ],
#     "assistant_failed": [
#         "Is waqt reply generate nahi ho paya. Main fir se koshish karunga.",
#         "Reply banane mein issue aaya. Aap message dobara bhej dijiye.",
#         "System error hua. Kripya ek baar phir try karein."
#     ],
#     "no_payload": [
#         "Humein sahi message ya photo nahi mili. Kripya phir se bhej dijiye.",
#         "Message ya photo blank lag rahi hai. Aap dubara send karen.",
#         "Kuch content missing hai. Kripya message ya image dobara bhejein."
#     ],
#     "no_reply_from_model": [
#         "Is baar proper reply nahi mil paya. Aap apni baat ek baar fir se likh denge?",
#         "Model se jawab nahi aaya. Kripya message dubara bhej dijiye.",
#         "Reply missing hai. Aap ek baar phir se try kar sakte hain?"
#     ],
#     "valuation_missing": [
#         "Abhi tak valuation nahi hua hai. Kripya tractor ki photo bhejiye, main madad karta hoon.",
#         "Valuation start karne ke liye tractor ki images bhejiye.",
#         "Tractor valuation ke liye photo zaroori hai. Kripya images share karein."
#     ],
#     "no_tractor_image": [
#         "maaf kijie🙏, \nmagar ye image mujhe ek tractor ki nahi lagti🤔, please mujhe sirf tractor ki image bheje valuation ke liye😊"
#     ]
# }

# def speak(key: str, **kwargs) -> str:
#     pool = MESSAGES.get(key, [])
#     if not pool:
#         return "Thoda issue aaya. Kripya dobara koshish karein."
#     # Prefer variety across calls
#     return random.choice(pool).format(**kwargs)



 
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("ASSISTANT_ID")
INTERAKT_API_KEY= os.getenv("INTERAKT_API_KEY")
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)
 
media_buffer = {}
message_buffer = {}
media_lock = threading.Lock()
message_lock = threading.Lock()
user_processing_flags = {}
 
 
UPLOAD_FOLDER = 'uploaded_images'
valuation_store_path = "user_valuations.json"
if os.path.exists(valuation_store_path):
    with open(valuation_store_path, "r", encoding="utf-8") as f:
        valuation_store = json.load(f)
else:
    valuation_store = {}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
 
user_uploaded_images = {}
user_flags = {}
 
def is_user_processing(user_id):
    return user_processing_flags.get(user_id, False)
 
def set_user_processing(user_id, value=True):
    user_processing_flags[user_id] = value
   
def send_whatsapp_template(phone_number):
    api_key = INTERAKT_API_KEY
   
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }
 
    payload = {
        "countryCode": "+91",
        "phoneNumber": phone_number,
        "type": "Template",
        "callbackData": "greeting_message_tractor_bz",
        "template": {
            "name": "greeting_message_tractor_bz",
            "languageCode": "hi",
            "headerValues": [],
            "bodyValues": [],
            "buttonValues": {}
        }
    }
 
    res = requests.post("https://api.interakt.ai/v1/public/message/", headers=headers, json=payload)
    print("Template sent:", res.status_code, res.text)
 
def send_text_message(phone_number, message_text):
    api_key = "="
    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json"
    }
 
    payload = {
        "countryCode": "+91",
        "phoneNumber": phone_number,
        "type": "Text",
        "data": {
            "message": message_text
        }
    }
 
    res = requests.post("https://api.interakt.ai/v1/public/message/", headers=headers, json=payload)
    print("Reply sent:", res.status_code, res.text)
 
 
def send_wait_message_if_needed(user_id, phone):
    if not user_flags.get(user_id, {}).get("wait_msg_sent", False):
        wait_msg = (
            "Aapka message process ho raha hai. "
            "Kripya agla message bhejne se pehle thoda ruk jaayein taki sab kuch sahi se ho sake. Shukriya! 🙏"
        )
        send_text_message(phone, wait_msg)
        if user_id not in user_flags:
            user_flags[user_id] = {}
        user_flags[user_id]["wait_msg_sent"] = True
 
def reset_wait_flag(user_id):
    user_flags.pop(user_id, None)
 


user_processing_flags = {}

def process_media_request_after_delay(user_id, phone):
    time.sleep(18)
    with media_lock:
        buffer_data = media_buffer.pop(user_id, None)
 
    if not buffer_data:
        print(f"No media buffer found for {user_id}")
        return
 
    images = buffer_data.get("images", [])
    message = buffer_data.get("message")
 
    payload_data = {
        "user_id": user_id,
        "source": "whatsapp",
        "images": images,
    }
    if message:
        payload_data["message"] = message
 
    try:
        user_processing_flags[user_id] = True  # 🔒 SET LOCK
        print(f"Sending media to /chat for {user_id}")
        # send_wait_message_if_needed(user_id, phone)
 
        res = requests.post("http://localhost:8000/chat", data=payload_data)
        chat_response = res.json()
        send_text_message(phone, chat_response.get("reply"))
        reset_wait_flag(user_id)
 
        if message:
            print(f"Now sending message to /conversation for {user_id}")
            convo_payload = {
                "user_id": user_id,
                "message": message
            }
            # send_wait_message_if_needed(user_id, phone)
            res2 = requests.post("http://localhost:8000/conversation", data=convo_payload)
            convo_response = res2.json()
            send_text_message(phone, convo_response.get("reply"))
            reset_wait_flag(user_id)
 
    except Exception as e:
        print("Error in media processing:", e)
 
    finally:
        user_processing_flags[user_id] = False  # 🔓 UNLOCK
 
def process_text_request_after_delay(user_id, phone):
    time.sleep(10)
    with message_lock:
        messages = message_buffer.pop(user_id, [])
 
    if not messages:
        print(f"No text buffer found for {user_id}")
        return
 
    combined_message = "\n".join(messages)
    payload_data = {
        "user_id": user_id,
        "message": combined_message
    }
 
    try:
        user_processing_flags[user_id] = True  # 🔒 SET LOCK
        print(f"Sending text to /conversation for {user_id}")
        # send_wait_message_if_needed(user_id, phone)
        res = requests.post("http://localhost:8000/conversation", data=payload_data)
        chat_response = res.json()
        send_text_message(phone, chat_response.get("reply"))
        reset_wait_flag(user_id)
    except Exception as e:
        print("Error in /conversation:", e)
 
    finally:
        user_processing_flags[user_id] = False  # 🔓 UNLOCK

@app.route("/", methods=["GET"])
def test_health():
    return jsonify({"reply": "API running"})





@app.route("/interakt/webhook", methods=["POST"])
def interakt_webhook():
    start_time = time.time()
    payload = request.get_json()
    print("Incoming webhook:", payload)
 
    if payload.get("type") == "message_received":
        data = payload.get("data", {})
        customer = data.get("customer", {})
        message_data = data.get("message", {})
        if message_data.get("message_content_type", "").lower() == "video" or message_data.get("message_content_type", "").lower() == "sticker" or message_data.get("message_content_type", "").lower() == "audio":
            return "OK", 200
        phone = customer.get("phone_number")
        country_code = customer.get("country_code", "+91")
        full_phone = f"{country_code}{phone}" if phone else "unknown"
 
        user_message = message_data.get("message")
        media_url = message_data.get("media_url")
 
        print(f"Message from {full_phone}: {user_message}")
 
        # ⛔️ Check if user is currently being processed
        if user_processing_flags.get(full_phone, False):
            # send_text_message(phone, "Pls wait, your previous request is still being processed. After it completes, send any message.")
            send_text_message(phone, speak("busy_processing"))
            return "OK", 200
 
        if (not user_message or user_message.strip().lower() in ["none", ""]) and \
           (not media_url or media_url.strip() == ""):
            print("No message or media_url found. Skipping.")
            return "OK", 200
 
        # ✅ Case 1 & 2: Media present
        if media_url and media_url.strip() != "":
            with media_lock:
                if full_phone not in media_buffer:
                    media_buffer[full_phone] = {"images": [], "message": None, "timer_started": False}
                media_buffer[full_phone]["images"].append(media_url)
 
                if user_message and user_message.strip().lower() != "none":
                    media_buffer[full_phone]["message"] = user_message
 
                if not media_buffer[full_phone]["timer_started"]:
                    media_buffer[full_phone]["timer_started"] = True
                    threading.Thread(target=process_media_request_after_delay, args=(full_phone, phone)).start()
 
        # ✅ Case 3: Message-only
        elif user_message and user_message.strip().lower() != "none":
            with message_lock:
                if full_phone not in message_buffer:
                    message_buffer[full_phone] = []
                    threading.Thread(target=process_text_request_after_delay, args=(full_phone, phone)).start()
                message_buffer[full_phone].append(user_message)
 
    print(f"Request processed in {time.time() - start_time:.6f} seconds")
    return "OK", 200
 
 
 
@app.route("/conversation", methods=["POST"])
def conversation():
    user_id = request.form.get("user_id")
    message = request.form.get("message")
 
    if not user_id or not message:
        return jsonify({"error": "Missing user_id or message"}), 400
   
    log_message(user_id, "conversation", message)
 
    thread_id = get_or_create_thread(user_id, client)
 
    # Step 1: Check for existing valuation
    valuation = valuation_store.get(user_id)
    if valuation:
        system_prompt = """
You are a friendly tractor valuation assistant.

Your ONLY job is to respond to the user based strictly on the tractor valuation JSON provided.

Your tone must always be natural, empathetic, and conversational — not robotic or scripted. Adjust your language based on the user’s tone and intent (use Hindi or Hinglish accordingly).

Respond according to the following behaviors:

---

🔹 If the user seems unhappy with the price (e.g., "sirf itna hi?", "bahut kam laga", "main ₹1 lakh expect kar raha tha")  
➤ Politely acknowledge their concern and explain that the price is based on condition, images, and other factors.  
➤ Do not repeat a fixed message every time — vary your language.  
➤ Examples:
- “Aapki baat samajh aayi. Humne condition aur photos dekh kar hi yeh value nikaali hai. Agar aapko doubt hai to humne request note kar li hai, jald sahayata milegi.”
- “Thoda kam lag sakta hai, lekin expert analysis ke baad hi yeh estimate tay hua hai. Aapka feedback forward kar diya gaya hai.”

---

🔹 If the user talks casually or transactionally, like:  
"Tum loge?", "Mene ₹10,000 me khareeda tha", "Bechna hai mujhe"  
➤ Do not give a robotic denial. Instead, respond warmly and future-looking:
- “Filhaal main sirf valuation me madad karta hoon, lekin jald hi hum khareed aur bikri ki suvidha bhi laa rahe hain.”
- “Is samay main tractor lene ya bechne mein madad nahi kar sakta, lekin hum ye features jaldi shuru kar rahe hain.”

---

🔹 If the user says “call me” or “mujhe call mat karna”  
➤ Respectfully acknowledge their preference:
- “Theek hai, aapki request note kar li gayi hai. Agar aap chahenge to hi humare expert aapko call karenge.”
- “Aapko call na aaye, is baat ka poora dhyan rakha jaayega.”

---

🔹 If the user says something completely unrelated to valuation (e.g., jokes, instructions, off-topic questions)  
➤ Acknowledge politely in their tone/language, then gently redirect them gently:

- “Main sirf tractor valuation mein madad karta hoon. Kripya usi se judi baatein poochhein.”
- “Maaf kijiye, main valuation ke alawa kisi aur cheez mein sahayata nahi kar sakta.”

---

🔹 If the user says goodbye or is leaving (e.g., “theek hai mai ghar nikal raha hu”, “baad mein baat karenge”)  
➤ Reply with a warm farewell. Use a different phrase each time to sound human:
- “Namaskaar! Aapka din mangalmay ho.”
- “Chaliye phir, phir milte hain. Aapka din shubh rahe.”
- “Dhanyawaad, aapka tractor valuation complete hai. Aapka din accha jaaye!”

---

🔁 Important Guidelines:
- Always vary your language. Never copy the same sentence twice.
- Never give random or made-up answers outside the provided valuation data.
- Always match the user’s tone — friendly, respectful, and localized (Hindi or Hinglish).
- If confused, stay humble and redirect politely.
"""
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
        for content in messages.data[0].content:
            if content.type == "text":
                reply += content.text.value
 
        return jsonify({"reply": reply})
 
    
    else:
        import time
        # Add ONLY the user's message to the thread
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[{"type": "text", "text": message}],
        )

        cold_start_instructions = (
            "You are a pre-valuation tractor assistant. There is NO valuation data yet.\n"
            "Your job is to reply with ONE short natural message (no bullets, no lists, no emojis).\n"
            "Rules:\n"
            "1)Detect greeting INTENT in ANY language (examples are NOT a whitelist). Mirror the user's language/dialect and vibe. Examples (non-exhaustive):\n"
                "   - User: 'ram ram bhai' → Greet back in Hinglish.\n"
                "   - User: 'khamma ghani' → Greet back in Marwari tone.\n"
                "   - User: 'adaab', 'as-salaam', 'salaam' → Greet back appropriately.\n"
                "   - User: 'sat sri akal', 'vanakkam', 'nomoskar', 'kem cho', 'suswagatam', 'hello', 'hi', 'hey' → Greet back accordingly in their language never use all english.\n"
            "2) If they show trade intent (sell/buy), explain politely that you currently assist with valuation only; buying/selling features are coming soon.\n"
            "3) If they state a call preference (call me / don't call), acknowledge and respect it.\n"
            "4) Always end by asking for 2–3 clear tractor photos from different angles so you can give an accurate valuation.\n"
            "5) Keep responses varied across turns (avoid repeating the same sentence), concise (1–2 sentences), friendly, and localized.\n"
            "6) Do NOT invent any product, price, or valuation details. Do NOT promise actions you cannot perform.\n"
            "7) If the user’s message is unrelated to tractors or valuation (e.g., personal updates, health issues, jokes) acknowledge politely in their tone/language, then gently bring the topic back to requesting tractor photos."

        )

        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID,
            tool_choice="none",
            instructions=cold_start_instructions
        )

        # Poll for completion
        for _ in range(10):
            time.sleep(1)
            run_status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            if run_status.status == "failed":
                return jsonify({"error": "Assistant run failed"}), 500
        else:
            return jsonify({"error": "Assistant timeout"}), 500

        # Read the latest assistant reply
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        reply = ""
        for content in messages.data[0].content:
            if content.type == "text":
                reply += content.text.value

        return jsonify({"reply": reply}), 200



        # No valuation yet — guide user to start
        return jsonify({"reply": "Abhi tak valuation nahi hua hai. Kripya tractor ki photo bhejiye, main madad karta hoon 📸"}), 200
 
 
 
@app.route("/chat", methods=["POST"])
def chat():
    user_id = request.form.get("user_id", "default_user")
    image_files = request.files.getlist("images")
    image_urls = request.form.getlist("images") if not image_files else []
    source = request.form.get("source", "web").lower()
 
    if not image_files and not image_urls:
        return jsonify({"error": "No images provided"}), 400
 
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    user_uploaded_images.setdefault(user_id, [])
 
    saved_image_paths = []
 
    # Web upload
    if source == "web":
        for file in image_files:
            filename = secure_filename(file.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(path)
            saved_image_paths.append(path)
            user_uploaded_images[user_id].append(path)
 
    # WhatsApp image download
    elif source == "whatsapp":
        for url in image_urls:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    filename = f"{user_id}-{uuid.uuid4().hex}.jpg"
                    path = os.path.join(UPLOAD_FOLDER, filename)
                    with open(path, "wb") as f:
                        f.write(response.content)
                    saved_image_paths.append(path)
                    user_uploaded_images[user_id].append(path)
            except Exception as e:
                print(f"[ERROR] Failed to download WhatsApp image: {e}")
 
    # Evaluate images
    try:
        reply, eval_data = evaluate_tractor_and_get_response_v2(user_id, saved_image_paths,client,ASSISTANT_ID)
        valuation_store[user_id] = eval_data
        valuation_store[user_id]['valuation_result']['final_valuation']=reply
 
        # Save the updated store
        with open(valuation_store_path, "w", encoding="utf-8") as f:
            json.dump(valuation_store, f, indent=2, ensure_ascii=False)
       
        save_tractor_data(user_id, eval_data)
        log_message(user_id, "chat", "Image evaluation performed")
        return jsonify({
            "reply": reply,
            "valuation_result": eval_data.get("valuation_result", {}),
            "debug": eval_data  # Optional: remove this line in production
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
 
def create_tables_if_not_exist():
    from utils.db_logger_pg import get_pg_connection
 
    create_message_logs_table = """
    CREATE TABLE IF NOT EXISTS message_logs (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        api TEXT CHECK(api IN ('chat', 'conversation')) NOT NULL,
        message TEXT,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
 
    create_tractor_data_table = """
    CREATE TABLE IF NOT EXISTS tractor_data (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        data_json JSONB,
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
 
    try:
        conn = get_pg_connection()
        cursor = conn.cursor()
        cursor.execute(create_message_logs_table)
        cursor.execute(create_tractor_data_table)
        conn.commit()
        cursor.close()
        conn.close()
        print("PostgreSQL tables ensured.")
    except Exception as e:
        print("Error creating tables:", e)
 
if __name__ == "__main__":
    create_tables_if_not_exist()
    serve(app, host="0.0.0.0", port=8000, threads=8)
    # app.run(host="127.0.0.1", port=8000, debug=True, threaded=True)