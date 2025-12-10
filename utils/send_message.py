import requests
def send_text_message(phone_number, message_text):
    api_key = ""
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
 