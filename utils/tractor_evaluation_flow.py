from dataclasses import dataclass
from openai import OpenAI
import openai
import os
from werkzeug.utils import secure_filename
import uuid
import requests
import base64
import tempfile
from utils.image_classifier import classify_image_type_bulk
from utils.brand_model_utils import predict_brand_model
from utils.number_plate_utils import extract_number_plate
from utils.rust_tire_utilsV2 import analyze_rust_tire
from utils.Vahan_payload import vahan_handler
from utils.top_price_utils import get_max_price_nearest_tractor
from utils.depreciation_func import evaluate_full_tractor_analysis
import json
from utils.send_message import send_text_message
from utils.choose_static import speak

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# ASSISTANT_ID = os.getenv("ASSISTANT_ID")
openai_api_key=os.getenv("OPENAI_API_KEY")

user_threads = {}

def download_urls_temporarily(urls):
    """Download URLs to temporary files and return paths"""
    temp_files = []
    for i, url in enumerate(urls):
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Create temporary file
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{i}.jpg")
                temp_file.write(response.content)
                temp_file.close()
                temp_files.append(temp_file.name)
                print(f"[INFO] Downloaded URL to temporary file: {temp_file.name}")
            else:
                print(f"[ERROR] Failed to download {url}: HTTP {response.status_code}")
        except Exception as e:
            print(f"[ERROR] Failed to download {url}: {e}")
    return temp_files

def generate_summary_with_chat_api(valuation_result, client: OpenAI):
    try:
        # Prefer vahan_data (if present later), fallback to brand_model_prediction
        brand = valuation_result.get("brand_model_prediction", {}).get("brand", "")
        model = valuation_result.get("brand_model_prediction", {}).get("model", "")
        brand_model_str = f"{brand} {model}".strip() if brand or model else "model nahi mila"

        # Rust details
        rust_data = valuation_result.get("rust_tire_analysis", {})
        rust_percent = rust_data.get("rust_percent", 0)
        rust_location = rust_data.get("rust_observation_text", "Rust location unavailable")

        # Tire details
        tires = rust_data.get("tires", {})
        tire_lines = []
        pos_map = {
            "front_left": "Front Left",
            "front_right": "Front Right",
            "rear_left": "Rear Left",
            "rear_right": "Rear Right"
        }
        for key in ["front_left", "front_right", "rear_left", "rear_right"]:
            percent = tires.get(key, {}).get("percent", 0)
            if isinstance(percent, str):
                percent=-99999
            if percent >= 80:
                status = "badiya halat mein hai"
            elif percent >= 60:
                status = "thoda ghisa hua hai"
            elif percent == -99999:
                status = "tasveer me dikhai nahi de rha"
            else:
                status = "kaafi purana lagta hai"
            tire_lines.append(f"*{pos_map[key]}*: {status} ({percent}%)")

        # Depreciation
        depreciation = valuation_result.get("valuation_result", {})
        total = depreciation.get("total_depreciation_percent", 0)
        rust_dep = depreciation.get("rust_depreciation", 0)
        # age_dep = depreciation.get("age_depreciation", 0)
        tire_dep = depreciation.get("tire_depreciation", 0)

        # Final price
        resale_value = depreciation.get("estimated_resale_price_inr", 0)
        resale_min = f"₹{int(resale_value):,}"
        resale_max = f"₹{int(resale_value + 15000):,}"

        # Final prompt
        prompt = f"""
        you are a friendly second hand tractor valuation agent powered up by openAI's gpt-4.
        your task is to change the information in tag <valuation>{...}<\valuation> to a user friendly valuation report that is being sent over whatsApp
        use emojis and whatsApp tone and understandable language to make the text more interpretable to indian farmers and remove the <tags> before sending final texts.
    


    <valuation>
    🚜 *Tractor Ka Andaja* 📋

    *Brand/Model*: {brand_model_str} lagta hai

    - *Zang ka haal*: {rust_percent}% rust hai, {rust_location}
    - *Tyre ki halat*:
        - {tire_lines[0]}
        - {tire_lines[1]}
        - {tire_lines[2]}
        - {tire_lines[3]}
    - *Depreciation ka andaja*:
        - Kul: {total}%
        - Zang: {rust_dep}%
        - Tyre se: {tire_dep}%

    👉 *Andajit Bikri Daam*: {resale_min} se {resale_max} 🚜💰
    <\valuation>

    
    """.replace("(-99999%)",'').strip()

        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Do not translate anything to English."},
                {"role": "user", "content": prompt}
            ]
        )
    except Exception as e:
        print(e)
        

    return response.choices[0].message.content.strip()


def encode_image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def handle_brand_model_error(brand_model_data, rust_tire_data):
    """
    Handle error when brand_model has different brands/models and rust_tire_data is empty
    
    Args:
        brand_model_data (dict): Dictionary containing brand and model information
        rust_tire_data (dict): Dictionary containing rust and tire analysis data
    
    Returns:
        str: Human-friendly error message in Hindi if conditions are met, None otherwise
    """
    # Check if rust_tire_data is empty
    if rust_tire_data == {}:
        # Check if brand_model has conflicting or invalid data
        brand = brand_model_data.get("brand", "")
        model = brand_model_data.get("model", "")
        
        # Check for different brands/models or invalid data
        if (brand == "" and model == "") or \
           (brand == "Generic" and model == "N/A") or \
           (brand != "" and model == "N/A") or \
           (brand == "N/A" and model != ""):
            
            return "Maaf kijie🙏,\nmagar ye image se mujhe jankari nikalne me kuch dikkat aarhi hai, please koi nayi photo ya koi doosre angle se tasveer bheje "
    
    return None


def upload_images_from_whatsapp(user_id, image_urls,client):
    uploaded_ids = []
    os.makedirs("uploaded_images", exist_ok=True)

    for url in image_urls:
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                filename = f"{user_id}-{uuid.uuid4().hex}.jpg"
                save_path = os.path.join("uploaded_images", filename)
                with open(save_path, "wb") as f:
                    f.write(response.content)

                with open(save_path, "rb") as f:
                    uploaded = client.files.create(file=f, purpose="vision")
                    uploaded_ids.append(uploaded.id)
        except Exception as e:
            print(f"[ERROR] Failed to download WhatsApp image: {e}")
    return uploaded_ids




def get_or_create_thread(user_id,client):
    if user_id in user_threads:
        return user_threads[user_id]
    thread = client.beta.threads.create()
    user_threads[user_id] = thread.id
    return thread.id

def upload_images_from_web(user_id, image_files,client):
    uploaded_ids = []
    os.makedirs("uploaded_images", exist_ok=True)

    for file in image_files:
        filename = secure_filename(file.filename)
        save_path = os.path.join("uploaded_images", filename)
        file.save(save_path)

        with open(save_path, "rb") as f:
            uploaded = client.files.create(file=f, purpose="vision")
            uploaded_ids.append(uploaded.id)
    return uploaded_ids

def evaluate_tractor_and_get_response_v2(user_id, image_paths,client,ASSISTANT_ID, vahan_data=None):
    

    thread_id = get_or_create_thread(user_id,client)

    # Step 1: classify images
    classified = classify_image_type_bulk(image_paths)
    
    # Create mapping between original paths/URLs and their classifications
    url_to_classification = {}
    for i, (filename, classification) in enumerate(classified):
        if i < len(image_paths):
            url_to_classification[image_paths[i]] = classification
    
    # Separate images by classification, handling both URLs and local paths
    tractor_imgs = []
    rc_imgs = []
    other_image = []
    toy_images = []
    
    for path_or_url in image_paths:
        classification = url_to_classification.get(path_or_url, "others")
        if classification == "tractor":
            tractor_imgs.append(path_or_url)
        elif classification == "RC document":
            rc_imgs.append(path_or_url)
        elif classification == "others":
            other_image.append(path_or_url)
        elif classification == "Toy":
            toy_images.append(path_or_url)

    brand_model = {}
    number_plate = ""
    rust_tire_data = {}
    vahan_data = vahan_data or {}  # Use passed vahan_data or initialize as empty
    top_price = {}
    final_valuation = {}
    age = 5

    trac_num  = len(tractor_imgs)
    rc_num    = len(rc_imgs)
    other_num = len(other_image)
    toy_num   = len(toy_images)

    # --- Step 1b: Build count message without zero categories -------------------
    parts = []
    if trac_num > 0:
        parts.append(f"{trac_num} tractor photo(s)")
    if rc_num > 0:
        parts.append(f"{rc_num} RC photo(s)")
    if other_num > 0:
        parts.append(f"{other_num} tasveeron mein humein tractor nahi dikh raha hai")
    if toy_num > 0:
        parts.append(f"{toy_num} khilone ki photo(s)")

    if parts:
        count_msg = "Aapki bheji hui photo(s) ka vivran:\n " + ",\n ".join(parts)


        print('USER PHONE NUMBER RECIEVED : ', user_id)
        send_text_message(user_id.replace('+91',''), count_msg) 

    # Step 2: tractor flow
    temp_files_to_cleanup = []
    
    if tractor_imgs:
        # Download tractor URLs temporarily for processing
        tractor_temp_files = []
        for tractor_img in tractor_imgs:
            if tractor_img.startswith(('http://', 'https://')):
                temp_files = download_urls_temporarily([tractor_img])
                tractor_temp_files.extend(temp_files)
                temp_files_to_cleanup.extend(temp_files)
            else:
                tractor_temp_files.append(tractor_img)
        
        try:
            brand_model = predict_brand_model(image_paths=tractor_temp_files)
        except: pass
        try:
            rust_tire_data = analyze_rust_tire(image_paths=tractor_temp_files)
        except: pass
        try:
            plate_results = extract_number_plate(tractor_temp_files)
            number_plate = next((res for res in plate_results if res and "not visible" not in res.lower()), "")
        except: pass

    # Step 3: RC fallback
    elif rc_imgs:
        # Download RC URLs temporarily for processing
        rc_temp_files = []
        for rc_img in rc_imgs:
            if rc_img.startswith(('http://', 'https://')):
                temp_files = download_urls_temporarily([rc_img])
                rc_temp_files.extend(temp_files)
                temp_files_to_cleanup.extend(temp_files)
            else:
                rc_temp_files.append(rc_img)
        
        try:
            plate_results = extract_number_plate(rc_temp_files)
            number_plate = next((res for res in plate_results if res and "not visible" not in res.lower()), "")
            print(number_plate)
            vah_res=vahan_handler(number_plate)
            fallback_humane_reply=vah_res['msg']
            # Clean up temporary files
            for temp_file in temp_files_to_cleanup:
                try:
                    os.unlink(temp_file)
                except:
                    pass
            return fallback_humane_reply, {
        "number_plate": number_plate,
        "vahan_data": vahan_data,
        "brand_model": brand_model,
        "rust_tire": rust_tire_data,
        "top_price": top_price,
        "valuation_result": final_valuation,
        "image_classification": classified
    }

        except: pass

    elif other_image:
        fallback_humane_reply="maaf kijie🙏, \nmagar ye image mujhe ek tractor ki nahi lagti🤔, please mujhe sirf tractor ki image bheje valuation ke liye😊"
        return speak("no_tractor_image"), {
    "number_plate": number_plate,
    "vahan_data": vahan_data,
    "brand_model": brand_model,
    "rust_tire": rust_tire_data,
    "top_price": top_price,
    "valuation_result": final_valuation,
    "image_classification": classified
}

    elif toy_images:
        fallback_humane_reply="Maaf kijie🙏,\nmagar ye image mujhe ek tractor ki nahi balki ek *khilone* ki lagi🤔, please ye mazaak na kre mujhe sirf *tractor* ki image bheje valuation ke liye😊"
        return fallback_humane_reply, {
    "number_plate": number_plate,
    "vahan_data": vahan_data,
    "brand_model": brand_model,
    "rust_tire": rust_tire_data,
    "top_price": top_price,
    "valuation_result": final_valuation,
    "image_classification": classified
}
    else:
        fallback_humane_reply="Maaf kijie🙏,\nmagar ye image se mujhe jankari nikalne me kuch dikkat aarhi hai, please koi nayi photo ya koi doosre angle se tasveer bheje "
        return fallback_humane_reply, {
    "number_plate": number_plate,
    "vahan_data": vahan_data,
    "brand_model": brand_model,
    "rust_tire": rust_tire_data,
    "top_price": top_price,
    "valuation_result": final_valuation,
    "image_classification": classified
}

    # Step 4: Vahan
    if number_plate:
        try:
            number_plate=number_plate.replace(' ','').replace('-','')
            vahan_data = vahan_handler(number_plate)
            age = int(vahan_data.get("age", 5))
        except: pass

    # first prkiority to RC parameter data , 2. vahan data which is below already , 3. tractor image has printed dataclass 
    # Step 5: Price lookup
    brand = vahan_data.get("Brand") or brand_model.get("brand", "")
    if(vahan_data.get("Brand")):
        brand_model['brand']=vahan_data.get("Brand")
    model = vahan_data.get("Model") or brand_model.get("model", "")
    if(vahan_data.get("Model")):
        brand_model['model']=vahan_data.get("Model")

    if brand and model:
        try:
            top_price = get_max_price_nearest_tractor(brand, model)
        except: pass

    # Step 6: Final valuation
    if rust_tire_data and top_price:
        try:
            final_valuation = evaluate_full_tractor_analysis(
                input_data={
                    "rust_tire_analysis": rust_tire_data,
                    "top_price_fuzzy_match": top_price,
                    "brand_model_prediction":brand_model
                },
                age_years=age
            )
        except: pass

    # Step 7: Assistant summary
    # Check for brand_model errors with empty rust_tire_data
    error_message = handle_brand_model_error(brand_model, rust_tire_data)
    if error_message:
        human_reply = error_message
        
        # Clean up temporary files
        for temp_file in temp_files_to_cleanup:
            try:
                os.unlink(temp_file)
            except:
                pass

        return human_reply, {
            "number_plate": number_plate,
            "vahan_data": vahan_data,
            "brand_model": brand_model,
            "rust_tire": rust_tire_data,
            "top_price": top_price,
            "valuation_result": final_valuation,
            "image_classification": classified
        }
    
    # Original condition for empty brand and model
    if((brand == '' and model == '') or rust_tire_data == {}):
        human_reply = "Maaf kijie🙏,\nmagar ye image se mujhe jankari nikalne me kuch dikkat aarhi hai, please koi nayi photo ya koi doosre angle se tasveer bheje "
        
        # Clean up temporary files
        for temp_file in temp_files_to_cleanup:
            try:
                os.unlink(temp_file)
            except:
                pass

        return human_reply, {
            "number_plate": number_plate,
            "vahan_data": vahan_data,
            "brand_model": brand_model,
            "rust_tire": rust_tire_data,
            "top_price": top_price,
            "valuation_result": final_valuation,
            "image_classification": classified
        }
    
    human_reply = generate_summary_with_chat_api(final_valuation, client)
    human_reply=human_reply.replace('<valuation>','').replace('<\valuation>','')

    # Clean up temporary files
    for temp_file in temp_files_to_cleanup:
        try:
            os.unlink(temp_file)
        except:
            pass

    return human_reply, {
        "number_plate": number_plate,
        "vahan_data": vahan_data,
        "brand_model": brand_model,
        "rust_tire": rust_tire_data,
        "top_price": top_price,
        "valuation_result": final_valuation,
        "image_classification": classified
    }
