# from flask import Flask
# from openai import OpenAI
# from dotenv import load_dotenv
# import os

# # load_dotenv()  # Load .env file

# print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
# print("ASSISTANT_ID:", os.getenv("ASSISTANT_ID"))

# load_dotenv(dotenv_path=r'.env.txt')

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# ASSISTANT_ID = os.getenv("ASSISTANT_ID")

# app = Flask(__name__)

# @app.route("/")
# def home():
#     return "OpenAI and Flask are configured correctly!"


from flask import Flask
from openai import OpenAI
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

# Check that they are loaded correctly
print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
print("ASSISTANT_ID:", os.getenv("ASSISTANT_ID"))

# Set up OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

app = Flask(__name__)

@app.route("/")
def home():
    return "OpenAI and Flask are configured correctly!"
