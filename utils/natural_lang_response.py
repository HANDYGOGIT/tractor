# import openai

# def generate_hindi_summary_with_gpt(evaluation_json: dict, openai_api_key: str, tone: str = "दोस्ताना"):
#     """
#     Generate a natural Hindi summary of tractor evaluation using GPT.

#     Args:
#         evaluation_json (dict): The full tractor evaluation JSON.
#         openai_api_key (str): Your OpenAI API key.
#         tone (str): Optional tone hint, like 'दोस्ताना', 'औपचारिक', 'WhatsApp शैली'.

#     Returns:
#         str: A short Hindi summary (80–90 words) covering rust, tire, and valuation details.
#     """

#     openai.api_key = openai_api_key

#     prompt = f"""
# तुम एक स्मार्ट एग्री मूल्यांकन सहायक हो। नीचे दिए गए ट्रैक्टर मूल्यांकन JSON के आधार पर 80 से 90 शब्दों में एक प्राकृतिक, संक्षिप्त और ग्राहक-अनुकूल हिंदी विवरण तैयार करो।

# इस विवरण में ट्रैक्टर की स्थिति, टायरों और जंग का अवलोकन, अनुमानित दोबारा बिक्री मूल्य, और मूल्य में आई गिरावट के मुख्य कारण शामिल करो। ज़रूरी हो तो तकनीकी शब्दों को सरल भाषा में समझाओ।

# ग्राहक का बैकग्राउंड ग्रामीण है, इसलिए जवाब {tone} भाषा में होना चाहिए।

# नीचे दिया गया जसों में से सिर्फ rust_tire_analysis और valuation_result की जानकारी का इस्तेमाल करे । इन्हें जरूर ध्यान में रखें।

# JSON:
# {evaluation_json}

# हिंदी में उत्तर दो:
# """

#     try:
#         response = openai.chat.completions.create(
#             model="gpt-3.5-turbo",
#             temperature=0.9,
#             messages=[
#                 {"role": "user", "content": prompt}
#             ]
#         )
#         response.choices[0].message.content.strip()
#         return response.choices[0].message.content.strip()
    
#     except Exception as e:
#         return f"[GPT Error]: {str(e)}"


# # summary = generate_hindi_summary_with_gpt(
# #     evaluation_json=tractor_data,
# #     openai_api_key="***REMOVED***...",  
# #     tone="दोस्ताना" 
# # )


import openai

def build_seed_sentence(evaluation_json,openai_api_key: str, tone: str = "दोस्ताना"):
    brand = evaluation_json.get("valuation_result", {}).get("brand", "")
    model = evaluation_json.get("valuation_result", {}).get("model", "")
    age = evaluation_json.get("vahan_details", {}).get("age", "")
    resale_price = evaluation_json.get("valuation_result", {}).get("estimated_resale_price_inr", 0)
    depreciation = evaluation_json.get("valuation_result", {}).get("total_depreciation_percent", 0)

    resale_in_lakhs = f"₹{round(resale_price, -3) // 100000}.{(round(resale_price, -3) % 100000) // 10000} लाख से ₹{round(resale_price+15000, -3) // 100000}.{(round(resale_price+15000, -3) % 100000) // 10000} लाख"

    rust_text = evaluation_json.get("rust_tire_analysis", {}).get("rust_observation_text", "")
    
    tires = evaluation_json.get("rust_tire_analysis", {}).get("tires", {})
    tire_texts = [
        tires.get("front_left", {}).get("text", ""),
        tires.get("front_right", {}).get("text", ""),
        tires.get("rear_left", {}).get("text", ""),
        tires.get("rear_right", {}).get("text", "")
    ]
    tire_summary = " ".join(tire_texts)

    seed_sentence = (
        f"{brand} {model} ट्रैक्टर की स्थिति का मूल्यांकन किया गया है। "
        f"{rust_text} "
        f"{tire_summary} "
        f"{age} साल पुराने इस ट्रैक्टर की अनुमानित दोबारा बिक्री कीमत लगभग {resale_in_lakhs} है। "
        f"इसमें कुल {depreciation}% तक मूल्य में गिरावट देखी गई है।"
    )

    # return seed_sentence


    # GPT prompt
    prompt = f"""
इस वाक्य को 80 से 90 शब्दों में {tone} भाषा में फिर से लिखो ताकि यह ग्राहक को ज़्यादा प्राकृतिक, आसान और भरोसेमंद लगे।
संख्यात्मक जानकारी (कीमत {resale_in_lakhs} और प्रतिशत {depreciation} है)।

"{seed_sentence}"
"""

    client = openai.OpenAI(api_key=openai_api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"[GPT Error]: {str(e)}"
