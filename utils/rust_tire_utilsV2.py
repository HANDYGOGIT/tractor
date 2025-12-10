import openai
import base64
import json
import re


openai.api_key = ""

def try_extract_json(text):
    # Remove code block markers
    if text.startswith("```json") or text.startswith("```"):
        text = re.sub(r"```(json)?", "", text).strip()
        text = text.rstrip("```").strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        print(" Failed to parse JSON:", e)
        return {}

def analyze_rust_tire(image_bytes_list=None, image_paths=None):
    if image_bytes_list is None and image_paths:
        image_bytes_list = []
        for path in image_paths:
            try:
                with open(path, "rb") as f:
                    image_bytes_list.append(f.read())
            except Exception as e:
                print(f"Error reading file {path}: {e}")




    base64_images = [base64.b64encode(img).decode("utf-8") for img in image_bytes_list]

    system_prompt = (
        "You are an expert in evaluating tractor condition. "
        "Only respond in JSON format as defined below and do not explain anything.\n\n"
        "Return a JSON with:\n"
        "- rust_percent: Estimated rust coverage as a percentage (0–100)\n"
        "- rust_observation_text: Text description of where rust is found and its severity\n"
        "- tires: Dictionary with keys front_left, front_right, rear_left, rear_right. "
        "Each should be an object with:\n"
        "  - percent: tire condition (0–100 or 'not_visible')\n"
        "  - text: description of that tire's condition\n\n"
        "Do not return markdown formatting. Do not wrap your response in code blocks."
    )

    # Build message payload
    messages = [{"role": "system", "content": system_prompt}]
    image_content = []

    for base64_img in base64_images:
        image_content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_img}",
                "detail": "high"
            }
        })

    messages.append({"role": "user", "content": image_content})

    # GPT-4o Vision Call
    response = openai.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        max_tokens=1000
    )

    gpt_output = response.choices[0].message.content.strip()
    print("\n[RAW GPT OUTPUT]\n", gpt_output)

    # Parse response
    parsed = try_extract_json(gpt_output)
    print("\n[PARSED JSON]\n", parsed)
    if(parsed=={}):
        vahan_message='आपकी दी गयी तस्वीरें एक ट्रेक्टर की तस्वीर नहीं लग रही, कृपया शमा करे, हम आपकी दी गयी तस्वीरो से आकलन नहीं निकाल पाए है। कृपया सही / साफ़ तस्वीर के साथ फिरसे प्रयास करे।'
        raise ValueError(vahan_message)

    return parsed
