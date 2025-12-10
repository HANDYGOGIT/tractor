import openai
import base64
import json


def classify_image_type_fast(image_file):
    """
    Classify an uploaded image (FileStorage) as 'tractor', 'RC document', 'Toy', or 'others' using the OpenAI Chat Completions API.
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

        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
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
)
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Classify this image."},
                        {"type": "image_url", "image_url": {"url": image_data_url}}
                    ]
                }
            ],
            max_tokens=16,
            temperature=0.3
        )
        raw_text = response.choices[0].message.content.strip()
        print("raw_text",raw_text)
        
        # Extract JSON from the response text
        start_idx = raw_text.find('{')
        end_idx = raw_text.rfind('}') + 1
        json_str = raw_text[start_idx:end_idx]
        raw_text = json.loads(json_str)

        raw_label = raw_text['classification'].lower()
        is_real = raw_text['is_real_photo']
        return allowed_labels.get(raw_label, "others"),is_real

    except Exception as e:
        print(f"Error classifying image: {e}")
        return "error"