from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import hashlib
import base64

def generate_key_from_password(password: str) -> bytes:
    sha512 = hashlib.sha512(password.encode('utf-8')).hexdigest()
    return sha512[:16].encode('utf-8')  # first 16 hex chars → UTF-8 → bytes

def decrypt_response_data(enc_text: str, password: str) -> str:
    try:
        encrypted_b64, iv_b64 = enc_text.split(":")
        encrypted_bytes = base64.b64decode(encrypted_b64)
        iv = base64.b64decode(iv_b64)

        aes_key = generate_key_from_password(password)
        cipher = AES.new(aes_key, AES.MODE_CBC, iv)
        decrypted_padded = cipher.decrypt(encrypted_bytes)
        decrypted = unpad(decrypted_padded, AES.block_size)
        return decrypted.decode('utf-8')
    except Exception as e:
        return f" Decryption failed: {str(e)}"
