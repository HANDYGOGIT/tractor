import base64
import openai
import json
import os


def extract_number_plate(image_paths):
    print('in extract number plate')
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    
    results = []
    for path in image_paths:
        if not os.path.exists(path):
            results.append(f"File not found: {path}")
            continue
        try:
            with open(path, "rb") as f:
                image_bytes = f.read()
        
    
            base64_image = base64.b64encode(image_bytes).decode("utf-8")

            prompt = [
                {"type": "text", "text": (
                    "Check the image carefully and extract the number written or painted on the tractor, especially if it's a number plate. "
                    "Only return the exact number you can clearly read. Do not guess or fill in missing parts. "
                    "If the number is unclear or not visible, respond with 'Number plate not visible or unclear'."
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]

            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )

            reply = response.choices[0].message.content.strip()
            results.append(reply)
        except Exception as e:
            print(f"Error processing {path}:", str(e))
            results.append(f"Error processing image: {os.path.basename(path)}")

    return results


def extract_number_plate_from_bytes(image_bytes_list):
    """
    Accepts a list of image bytes (not file paths), sends each to GPT-4o Vision
    for number plate extraction, and returns a list of extracted numbers or error messages.
    """
    print('in extract_number_plate_from_bytes')
 
    results = []
    for idx, image_bytes in enumerate(image_bytes_list):
        try:
            base64_image = base64.b64encode(image_bytes).decode("utf-8")
            print("---------------------")
            prompt = [
                {"type": "text", "text": (
                    "Check the RC document, and extract the RC document, registration number from the document"
                    "Return just the extracted registration number "
                )},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]
 
            response = openai.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100
            )
            print(response)
            reply = response.choices[0].message.content.strip()
            results.append(reply)
 
        except Exception as e:
            print(f"Error processing image index {idx}:", str(e))
            results.append(f"Error processing image {idx}: {str(e)}")
 
    return results
 