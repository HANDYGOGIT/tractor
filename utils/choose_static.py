import random


# =========================
# Humanized message pools
# =========================
MESSAGES = {
    "wait": [
        "Aapka message process ho raha hai. Kripya kuch der ruk jaiye.",
        "Main abhi aapke message par kaam kar raha hoon. Thodi der dein.",
        "Request receive ho gayi hai, processing chal rahi hai. Bas thoda sa time.",
        "Note kar liya hai—processing mein hai. Kripya thoda sa intazaar karein."
    ],
    "busy_processing": [
        "Aapka pehle wale message par kaam chal raha hai 😊 Kripya thoda sa intezaar karein 🙏.",
        "Abhi message ki ek request chal rahi hai 😊Jaise hi poori hogi, aapki agli request li jaayegi 🙏",
        "Hum aapke pichle message par kaam kar rahe hai. Naya message bhejne se pehle kuch der intezaar karein.",
        "Bhai, bas thodi der ka intezaar aur kar lijiye 🙏",
        "Pehle wala message abhi process ho raha hai. Kripya thoda intazaar karen.",
        "Abhi ek request chal rahi hai. Jaise hi khatam hogi, aapka agla message le lunga.",
        "System aapke last message par kaam kar raha hai. Naya message bhejne se phle kuch deer intezaare kre.",
        "Kuch der ruko bhai "
    ],
    "media_processing_error": [
        "Media process karte waqt dikkat aayi. Aap dobara koshish karen, main madad karta hoon.",
        "Image ko process karte hue error aaya. Kripya ek baar dubara bhej dijiye.",
        "Maaf kijiye, photo par kaam karte waqt issue aaya. Aap phir se bhej sakte hain?"
    ],
    "conversation_error": [
        "Reply tayar karte waqt dikkat aayi. Aap apna message dobara bhej sakte hain?",
        "System ko reply generate karne mein problem hui. Kripya dobara try karein.",
        "Thoda issue aa gaya. Aapka message dubara share kar denge?"
    ],
    "assistant_timeout": [
        "Reply aane mein zyada time lag raha hai. Main phir se try kar raha hoon.",
        "System response slow hai. Kripya thodi der baad dobara koshish karein.",
        "Lagta hai response me der ho rahi hai. Aap thoda intazaar karein ya phir se bhejein."
    ],
    "assistant_failed": [
        "Is waqt reply generate nahi ho paya. Main fir se koshish karunga.",
        "Reply banane mein issue aaya. Aap message dobara bhej dijiye.",
        "System error hua. Kripya ek baar phir try karein."
    ],
    "no_payload": [
        "Humein sahi message ya photo nahi mili. Kripya phir se bhej dijiye.",
        "Message ya photo blank lag rahi hai. Aap dubara send karen.",
        "Kuch content missing hai. Kripya message ya image dobara bhejein."
    ],
    "no_reply_from_model": [
        "Is baar proper reply nahi mil paya. Aap apni baat ek baar fir se likh denge?",
        "Model se jawab nahi aaya. Kripya message dubara bhej dijiye.",
        "Reply missing hai. Aap ek baar phir se try kar sakte hain?"
    ],
    "valuation_missing": [
        "Abhi tak valuation nahi hua hai. Kripya tractor ki photo bhejiye, main madad karta hoon.",
        "Valuation start karne ke liye tractor ki images bhejiye.",
        "Tractor valuation ke liye photo zaroori hai. Kripya images share karein."
    ],
    "no_tractor_image": [
        "maaf kijie🙏, \nmagar ye photo mujhe ek tractor ki nahi lagti🤔, please mujhe sirf tractor ki photo bheje valuation ke liye😊",
        "Bhai, yeh bheji hui tasveer tractor ki hai kya? 🤔\n Mujhe yeh tractor ki nahi lag rahi… Kripya tractor ki hi tasveer bhejein 🙏🙏."
    ],
    "toy_image": [
        "Maaf kijie🙏,\nmagar ye photo mujhe ek tractor ki nahi balki ek *khilone* ki lagi🤔, please ye mazaak na kre mujhe sirf *tractor* ki image bheje valuation ke liye😊",
        "Maaf kijiye 🙏, lekin yeh photo tractor ki nahi lag rahi 🤔. Kripya sirf tractor ki photo bhej dijiye taaki hum valuation kar saken 😊."
        ]
}

def speak(key: str, **kwargs) -> str:
    pool = MESSAGES.get(key, [])
    if not pool:
        return "Thoda issue aaya. Kripya dobara koshish karein."
    # Prefer variety across calls
    return random.choice(pool).format(**kwargs)