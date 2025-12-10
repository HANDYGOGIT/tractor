import json
import logging
import os
from utils.Vahan_payload import vahan_handler
from utils.rust_tire_utilsV2 import analyze_rust_tire
from utils.number_plate_utils import extract_number_plate
from utils.brand_model_utils import predict_brand_model
from utils.top_price_utils import get_max_price_nearest_tractor
from utils.depreciation_func import evaluate_full_tractor_analysis
from utils.image_classifier import classify_image_type_bulk

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    filename="logs/tool_call_debug.log",
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    filemode="a"  
)

def list_full_paths(folder_path):
    return [os.path.join(folder_path, name) for name in os.listdir(folder_path)]

def is_folder_empty(folder_path):
    return not os.listdir(folder_path)

def handle_tool_calls(client, thread_id, run, tool_calls,local_img_path):
    global rust_tire_fallback,fuzzy_response
    """
    Handles all tool_calls issued by OpenAI Assistant API for a given run.

    Parameters:
    - client: OpenAI API client
    - thread_id: ID of the thread
    - run: the current run object
    - tool_calls: list of tool_call objects from run

    Returns:
    - None (but submits tool outputs back to OpenAI)
    """

    tool_outputs = []
    RC_folder=r'D:\tractor_assistan_V3\classified_images\rc'
    tractor_images=r'D:\tractor_assistan_V3\classified_images\tractor'

    for tool_call in tool_calls:
        fn_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        print(f"\n  [Tool Call] Function: {fn_name}")
        print(f"  Arguments:\n{json.dumps(args, indent=2)}")

        logging.info(f"Tool Call: {fn_name}")
        logging.info(f"Arguments:\n{json.dumps(args, indent=2)}")

        try:
            if fn_name == "vahan_handler":
                result = vahan_handler(args["rc_number"])

            elif fn_name == "analyze_rust_tire":
                result = analyze_rust_tire(image_paths=list_full_paths(tractor_images))
                rust_tire_fallback=result
            elif fn_name == "extract_number_plate":
                if not is_folder_empty(RC_folder):
                    result = extract_number_plate(list_full_paths(RC_folder))
                else:
                    result = extract_number_plate(list_full_paths(tractor_images))

            elif fn_name == "predict_brand_model":
                result = predict_brand_model(image_paths=list_full_paths(tractor_images))

            elif fn_name == "get_max_price_nearest_tractor":
                result = get_max_price_nearest_tractor(
                    args["brand"],
                    args["model"]
                )
                fuzzy_response=result

            # elif fn_name == "evaluate_full_tractor_analysis":
            #     result = evaluate_full_tractor_analysis(
            #         args["brand"],
            #         args["model"],
            #         args["KM_driven"],
            #         args["rust_condition"],
            #         args["tire_condition"],
            #         args["rc_verified"],
            #         args["age"]
            #     )

            elif fn_name == "evaluate_full_tractor_analysis":
                result = evaluate_full_tractor_analysis(input_data={"rust_tire_analysis":args["rust_tire_analysis"],
                                                                    "top_price_fuzzy_match":args["top_price_fuzzy_match"]
                                                                    },

                    age_years=args["age_years"]
                )
                if(result=={
                            "rust_tire_analysis": {},
                            "top_price_fuzzy_match": {}
                            }):
                    print('evaluate_full_tractor_analysis failed, proceeding with raw call')
                    result = evaluate_full_tractor_analysis(input_data={"rust_tire_analysis":rust_tire_fallback,
                                                                    "top_price_fuzzy_match":fuzzy_response
                                                                    }, age_years=args["age_years"]
                )
                    
                    

            elif fn_name == "classify_image_type_bulk":
                image_paths = local_img_path
                classification_list = classify_image_type_bulk(image_paths)

                # def safe_class(cls):
                #     cls = cls.lower()
                #     if "rc" in cls:
                #         return "RC"
                #     elif "tractor" in cls:
                #         return "Tractor"
                #     else:
                #         return "others"

                result = {
                    "image_classification": classification_list
                }

            else:
                result = {"error": f"Unknown function name: {fn_name}"}

            print(f" [Result] {fn_name} output:\n{json.dumps(result, indent=2)}")
            logging.info(f"Result for {fn_name}:\n{json.dumps(result, indent=2)}")

        except Exception as e:
            result = {"error": f"Exception while calling {fn_name}: {str(e)}"}
            print(f" [Error] {fn_name} failed:\n{str(e)}")
            logging.error(f"Error in {fn_name}: {str(e)}")

        tool_outputs.append({
            "tool_call_id": tool_call.id,
            "output": json.dumps(result)
        })

    # Submit tool outputs back to assistang
    client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run.id,
        tool_outputs=tool_outputs
    )
