
import os
import time
from openai import OpenAI
from dotenv import load_dotenv
import json
import re
# from app import try_extract_json  # used to parse assistant JSON

load_dotenv(dotenv_path=r'D:\tractor_assistant\.env.txt')

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# In-memory cache per user (for demo only)
user_threads = {}
user_state = {}  # { user_id: { "vahan_fetched": False, "rc_number": None } }

# def try_extract_json(text):
#     match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
#     if not match:
#         return {}
#     json_str = match.group(1)
#     try:
#         return json.loads(json_str)
#     except json.JSONDecodeError as e:
#         print("Failed to parse JSON:", e)
#         return {}

def try_extract_json(text):
    if isinstance(text, tuple):
        text = " ".join([str(t) for t in text if t])
    elif not isinstance(text, str):
        return {}

    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not match:
        return {}
    
    json_str = match.group(1)
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("Failed to parse JSON:", e)
        return {}




def get_or_create_thread(user_id: str):
    if user_id not in user_threads:
        thread = client.beta.threads.create()
        user_threads[user_id] = thread.id
    return user_threads[user_id]

def upload_image(image_path):
    file = client.files.create(file=open(image_path, "rb"), purpose="assistants")
    return file.id

# def send_message_to_assistant(user_id, message_text, image_path=None):
    thread_id = get_or_create_thread(user_id)

    # Build content with message text and optional image
    content = [{"type": "text", "text": message_text}]
    if image_path:
        image_id = upload_image(image_path)  # Upload to OpenAI
        # Attach image to message content
        content.append({
            "type": "image_file",
            "image_file": { "file_id": image_id }
        })

    # Step 1: Send user message
    client.beta.threads.messages.create(thread_id=thread_id, role="user", content=content)

    # Step 2: Run assistant
    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=os.getenv("ASSISTANT_ID"))

    # Step 3: Wait for run to complete
    while True:
        status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id).status
        if status == "completed":
            break
        time.sleep(1)

    # Step 4: Get assistant reply
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    assistant_messages = [msg for msg in messages.data if msg.role == "assistant"]
    last_msg = assistant_messages[0].content[0].text.value

    # Step 5: Try parsing JSON to extract number_plate
    parsed_json = try_extract_json(last_msg)
    number_plate = parsed_json.get("number_plate", "")

    # Step 6: Vahan API logic — trigger once after number_plate is captured
    if user_id not in user_state:
        user_state[user_id] = {"vahan_fetched": False, "rc_number": None}

    if number_plate and not user_state[user_id]["vahan_fetched"]:
        # Call Vahan API using your handler
        from utils.Vahan_payload import vahan_handler
        vahan_data = vahan_handler(number_plate)

        # Save to user state to prevent multiple calls
        user_state[user_id]["vahan_fetched"] = True
        user_state[user_id]["rc_number"] = number_plate

        # Step 7: Inject Vahan data into assistant thread silently
        if vahan_data:
            hidden_context = f"<vahan_details>{json.dumps(vahan_data)}</vahan_details>\n"
            message_text = hidden_context + message_text
        
        content = [{"type": "text", "text": message_text}]
        client.beta.threads.messages.create(thread_id=thread_id, role="user", content=content)


        # system_message = {
        #     "role": "system",
        #     "content": [{
        #         "type": "text",
        #         "text": json.dumps({"vahan_details": vahan_data})
        #     }]
        # }
        # client.beta.threads.messages.create(thread_id=thread_id, **system_message)

        # Step 8: Rerun assistant to let it use Vahan info
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=os.getenv("ASSISTANT_ID"))

        while True:
            status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id).status
            if status == "completed":
                break
            time.sleep(1)

        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_msg = messages.data[0].content[0].text.value

    return last_msg  # Final assistant reply (with Vahan info if injected)
def send_message_to_assistant(user_id, message_text, image_paths=None,tractor_analysis=None):
    from app_legacy import try_extract_json
    from utils.Vahan_payload import vahan_handler
    import time, json, os
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    thread_id = get_or_create_thread(user_id)

    # Maintain user state in memory
    state = user_state.setdefault(user_id, {
        "vahan_fetched": False,
        "rc_number": None
    })

    # Build user message content
    content = [{"type": "text", "text": message_text}]
    hidden_context = ""
    # if image_path:
    #     image_id = upload_image(image_path)
    #     content.append({"type": "image_file", "image_file": {"file_id": image_id}})

    if image_paths:
        for path in image_paths:
            image_id = upload_image(path)
            content.append({"type": "image_file", "image_file": {"file_id": image_id}})

    # Step 1: Send user message to thread
    client.beta.threads.messages.create(thread_id=thread_id, role="user", content=content)

    # Step 2: Run assistant
    run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=os.getenv("ASSISTANT_ID"))
    while True:
        status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id).status
        if status == "completed":
            break
        time.sleep(1)

    # Step 3: Read latest assistant reply
    messages = client.beta.threads.messages.list(thread_id=thread_id)
    assistant_messages = [msg for msg in messages.data if msg.role == "assistant"]
    last_msg = assistant_messages[0].content[0].text.value

    # Step 4: Extract structured data from assistant
    parsed = try_extract_json(last_msg)
    number_plate = parsed.get("number_plate")
    rc_verified = parsed.get("rc_verified", False)
    

    # if(tractor_analysis):
    #     hidden_context=f"<rust_tire_condition>{json.dumps(tractor_analysis)}</rust_tire_condition>\n"
    # # Update state if new RC detected
    # if number_plate and not state["rc_number"]:
    #     state["rc_number"] = number_plate
    if tractor_analysis:
        state["tractor_analysis"] = tractor_analysis  # store for reuse
        hidden_context += f"<rust_tire_condition>{json.dumps(tractor_analysis)}</rust_tire_condition>\n"
    elif state.get("tractor_analysis"):
        hidden_context += f"<rust_tire_condition>{json.dumps(state['tractor_analysis'])}</rust_tire_condition>\n"

    if number_plate and not state["rc_number"]:
        state["rc_number"] = number_plate

    # Step 5: If RC verified, trigger Vahan API (only once)
    if rc_verified and not state["vahan_fetched"] and state["rc_number"]:
        vahan_data = vahan_handler(state["rc_number"])
        state["vahan_fetched"] = True

        # Inject Vahan data silently in <vahan_details>{}</vahan_details>
        hidden_context = hidden_context+f"<vahan_details>{json.dumps(vahan_data)}</vahan_details>\n"
        message_text = hidden_context + message_text

        # Send new message with Vahan data
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=[{"type": "text", "text": message_text}]
        )

        # Run assistant again to absorb Vahan details
        run = client.beta.threads.runs.create(thread_id=thread_id, assistant_id=os.getenv("ASSISTANT_ID"))
        while True:
            status = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id).status
            if status == "completed":
                break
            time.sleep(1)

        # Get updated assistant message
        messages = client.beta.threads.messages.list(thread_id=thread_id)
        last_msg = messages.data[0].content[0].text.value

    return last_msg,hidden_context


def classify_image_type_bulk(image_paths):
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    
    prompt = "For each image, reply with either RC or Tractor based on its content. Respond in this exact format as JSON: [\"RC\", \"Tractor\", ...]"

    vision_inputs = [{"type": "text", "text": prompt}]
    for image_path in image_paths:
        file = client.files.create(file=open(image_path, "rb"), purpose="assistants")
        vision_inputs.append({"type": "image_file", "image_file": {"file_id": file.id}})

    thread = client.beta.threads.create()
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=vision_inputs)

    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=os.getenv("ASSISTANT_ID"))

    while True:
        status = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id).status
        if status == "completed":
            break
        time.sleep(1)

    messages = client.beta.threads.messages.list(thread_id=thread.id)
    response = messages.data[0].content[0].text.value.strip()

    try:
        match = re.search(r"```json\s*(\[[^\]]*\])\s*```", response, re.DOTALL)
        if match:
            json_str = match.group(1)
            classifications = json.loads(json_str)
            return classifications
        else:
            # Fallback: try loading raw response if not wrapped in ```json
            return json.loads(response)
        # classifications = json.loads(response)
        # return classifications  # List like: ["RC", "Tractor", "Tractor"]
    except:
        return ["Tractor"] * len(image_paths)  # Fallback default
