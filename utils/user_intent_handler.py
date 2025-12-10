import json
from utils.Vahan_payload import vahan_handler
# from utils.valuation_store import valuation_store  # assumes you created the in-memory store

def handle_user_intent(user_id, valuation_store, intent=None, rc_number=None):
    responses = []

    if intent == "start_evaluation":
        responses.append("Aap apne tractor ki photo bhejiye, valuation ke liye. 📸")

    elif intent == "valuation_question":
        valuation = valuation_store.get(user_id)
        if valuation:
            val = valuation.get("valuation_result", {})
            rust = valuation.get("rust_tire", {})
            val_price_range = val.get("valuation_result", "N/A")
            
            brand_model = valuation.get("brand_model", {})
            price_range=val_price_range.get("estimated_resale_price_inr",{})
            vahan = valuation.get("vahan_data", {})

            summary = []

            summary.append("✅ Yeh hai aapke tractor ka valuation summary:")

            if brand_model:
                summary.append(f"- **Brand/Model:** {brand_model.get('brand', '')} {brand_model.get('model', '')}".replace("Unknown",""))

            if rust:
                summary.append(f"- **Rust Status:** {rust.get('rust_percent', 'N/A')}")
                summary.append(f"- **Rust Remarks** {rust.get('rust_percent', 'N/A')}")
                summary.append(f"- **Tire Condition:** Front Left: {rust.get('front_left', 'N/A')},Front Right: {rust.get('front_right', 'N/A')}, Rear Left: {rust.get('rear_left', 'N/A')}, Rear Right: {rust.get('rear_right', 'N/A')}")

            if val:
                summary.append(f"- **Estimated Resale Value:** ₹{price_range} - ₹{int(price_range)+15000}(approx) 💰")

            if vahan:
                summary.append(f"- **RC Info:** {vahan.get('Brand', '')} {vahan.get('Model', '')}, Age: {vahan.get('age', '')} yrs")

            summary.append("Kuch aur puchhna hai toh poochh sakte ho. 😊")

            responses.append("\n".join(summary))
        else:
            responses.append("Abhi tak valuation nahi hua hai. Kripya photo bhejiye.")


    elif intent == "revaluation_requested":
        responses.append("Thik hai. Naye images bhejiye, main dobara valuation kar dunga.")

    elif intent == "rc_number_provided" and rc_number:
        try:
            from utils.Vahan_payload import vahan_handler
            data = vahan_handler(rc_number)
            valuation_store[user_id] = {"vahan_data": data}
            responses.append(f"RC data mil gaya ✅:\n{json.dumps(data, indent=2, ensure_ascii=False)}")
        except Exception:
            responses.append("RC number process nahi ho paya. Dubara koshish karein.")

    elif intent == "off_topic":
        responses.append("maaf kijie, Main sirf tractor valuation mein madad karta hoon 🙏")

    elif intent == "greeting":
        responses.append("Namaste! Main aapki tractor valuation mein madad karta hoon. Kripya tractor ya RC ki photo 📋")

    else:
        responses.append("Mujhe samajh nahi aaya. Kripya dobara batayein.")

    return {"reply": "\n\n".join(responses)}
