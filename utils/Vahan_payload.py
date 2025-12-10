import hashlib
import base64
import json
from flask import jsonify
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
import os
from utils.Vahan_response_dycrp import decrypt_response_data

def generate_key_from_password(password: str) -> bytes:
    sha512 = hashlib.sha512(password.encode('utf-8')).hexdigest()  # hex string
    key_hex = sha512[:16]  # First 16 chars of hex string
    return key_hex.encode('utf-8')  # Convert to bytes

def encrypt_request_data(password: str, trans_id: str, doc_type: int, doc_number: str) -> str:
    aes_key = generate_key_from_password(password)
    iv = os.urandom(16)  # random 16-byte IV

    # Step 2: JSON structure
    data = {
        "transID": trans_id,
        "docType": str(doc_type),
        "docNumber": doc_number
    }
    json_string = json.dumps(data, separators=(',', ':'))

    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    padded = pad(json_string.encode('utf-8'), AES.block_size)
    encrypted = cipher.encrypt(padded)

    encrypted_b64 = base64.b64encode(encrypted).decode('utf-8')
    iv_b64 = base64.b64encode(iv).decode('utf-8')
    return f"{encrypted_b64}:{iv_b64}"

# password = "India@2608"
# trans_id = "1234565"
# doc_type = 19
# doc_number = "UP53CP8880"
# url = "https://www.truthscreen.com/api/v2.2/utilitysearch"
# headers = {
#     "username": "production@behtarzindagi.in",
#     "Content-Type": "application/json"
# }

# request_data = encrypt_request_data(password, trans_id, doc_type, doc_number)
# payload = {
#     "requestData": request_data
# }
# print("Request payload:", payload)

# response = requests.post(url, headers=headers, json=payload)
# print("Raw response:", response)

# response_json = response.json()
# if "responseData" in response_json:
#     encrypted_response = response_json["responseData"]
#     decrypted_json_str = decrypt_response_data(encrypted_response, password)
#     try:
#         decrypted_json = json.loads(decrypted_json_str)
#     except Exception:
#         decrypted_json = decrypted_json_str
#     print("Decrypted JSON:")
#     print(json.dumps(decrypted_json, indent=2, ensure_ascii=False) if isinstance(decrypted_json, dict) else decrypted_json)
# else:
#     print("No responseData found in response:", response_json)
import datetime

def payload_render(test):
    
    print('here \n',test)
    vehical_pay={}
    vehical_pay['RC_number']=test["msg"]["Registration Number"]
    vehical_pay['age']=datetime.date.today().year-int(test['msg']['Registration Date'].split('/')[-1])
    vehical_pay["owner_name"]=test['msg']["Owner's Name"]
    vehical_pay['Model']=test['msg']["Model / Maker's Class"]
    vehical_pay['status']=test['status']
    vehical_pay['Brand']=test['msg']['Maker / Manufacturer']
    if('swaraj'in test['msg']['Maker / Manufacturer'].lower()):
        vehical_pay['Brand']='Swaraj'
    if('punjab tractors limited'in test['msg']['Maker / Manufacturer'].lower()):
        vehical_pay['Brand']='Swaraj'


    return vehical_pay


def vahan_handler(number):
    try:
        print(number)
        password = ""
        trans_id = "123456566"
        doc_type = 19
        doc_number = number.upper().replace('-','')
        url = "https://www.truthscreen.com/api/v2.2/utilitysearch"
        headers = {
            "username": "",
            "Content-Type": "application/json"
        }
        request_data = encrypt_request_data(password, trans_id, doc_type, doc_number)
        payload = {
            "requestData": request_data
        }
        response = requests.post(url, headers=headers, json=payload)
        response_json = response.json()
        # if "responseData" in response_json:
        encrypted_response = response_json["responseData"]
        decrypted_json_str = decrypt_response_data(encrypted_response, password)
        print('***********************\n',decrypted_json_str)
        try:
            decrypted_json = json.loads(decrypted_json_str)
        except Exception:
            decrypted_json = decrypted_json_str
        print("Decrypted JSON:")
        if(decrypted_json['status']==1):
            msg = decrypted_json.get("msg")
            if isinstance(msg, dict):
                # if msg.get("Vehicle Class") != "Agricultural Tractor":
                if("tractor" not in msg.get("Vehicle Class").lower()):
                    vahan_message='आपके द्वारा बता गए RC से ये प्रतीत होता है की यह एक ट्रेक्टर नहीं बल्कि एक {} का नंबर है। कृपया ट्रेक्टर की उम्र बताके पुनः प्रयास करे।'.format(msg.get("Vehicle Class"))
                    return {'error':"not a tractor","msg":vahan_message}
                    raise ValueError(vahan_message)
        else:
            vahan_message='आपके द्वारा बताइये गए RC से आपके ट्रेक्टर की जानकारी प्राप्त नहीं हो सकी है, कृपया ट्रेक्टर की तस्वीरें और उम्र बताके पुनः प्रयास करे।'
            return {'error':"RC not found","msg":vahan_message}
            raise ValueError(vahan_message)

        return payload_render(decrypted_json)
        #  vahan_response=payload_render(decrypted_json)
        # return vahan_response
        # else:
        #     print("No responseData found in response:", response_json)
        #     return response_json

    except Exception as e:
        raise RuntimeError(f"{str(e)}")


