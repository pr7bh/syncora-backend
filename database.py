import os

from dotenv import load_dotenv
from pymongo import AsyncMongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DATABASE_NAME = os.getenv("DATABASE_NAME", "syncora")

client = AsyncMongoClient(MONGO_URI)

db = client[DATABASE_NAME]

users_collection = db["users"]
meetings_collection = db["meetings"]
otp_collection = db["otp_codes"]