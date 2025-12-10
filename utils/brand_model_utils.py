# utils/brand_model.py
import base64
import openai
import json
import re
import ast
import json



def extract_brand_model_json(content):
    try:
        
        start_index = content.find('{')
        if start_index == -1:
            return {}

        
        brace_count = 0
        for i in range(start_index, len(content)):
            if content[i] == '{':
                brace_count += 1
            elif content[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    end_index = i + 1
                    break
        else:
            return {}

        json_block = content[start_index:end_index]

        
        parsed = ast.literal_eval(json_block)

        
        return json.loads(json.dumps(parsed))
    except Exception as e:
            print(" Failed to extract JSON:", e)
            return {}




def predict_brand_model(image_bytes_list=None, image_paths=None):
    if image_bytes_list is None and image_paths:
        image_bytes_list = []
        for path in image_paths:
            try:
                with open(path, "rb") as f:
                    image_bytes_list.append(f.read())
            except Exception as e:
                print(f"Error reading file {path}: {e}")

    base64_images = [base64.b64encode(img).decode("utf-8") for img in image_bytes_list]

    		
    messages = [{
                                "role": "system",
                                "content": (
                                    "You are a highly skilled tractor expert and assistant. "
                                    "You are shown a photo of a tractor and asked to identify its brand, model, and resale price. "
                                    "Use visual cues such as logos, shape, headlight style, and color to make an educated guess. "
                                    "Do not say 'Unknown' unless absolutely nothing can be inferred."
                                )
                            },{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": (
                        "Please identify the tractor's brand and model from the images. "
                        "Also, based on visible condition (paint, rust, tires), estimate the resale price in INR. "
                        "Return your response as natural explanation text followed by a JSON block with keys in the following format: "
                        "sample : {'brand': "",'model': "",'price_estimation': ""}"
                    )
                }
            ] + [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}} for img in base64_images]
        }]

    response = openai.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=500
        )
    

    
    content = response.choices[0].message.content.strip()
    result = extract_brand_model_json(content)
    match = re.search(r'\{.*?\}', content, re.DOTALL)
    if result:
        print('===================================')
        print(result)
        return result
    return {}
