from datetime import datetime
import os

from dotenv import load_dotenv
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

_mongo_username = os.getenv("MONGODB_USERNAME")
_mongo_password = os.getenv("MONGODB_PASSWORD")
if not _mongo_username or not _mongo_password:
    raise RuntimeError("Missing MONGODB_USERNAME or MONGODB_PASSWORD environment variable.")

_mongo_uri = (
    "mongodb+srv://"
    f"{_mongo_username}:{_mongo_password}"
    "@cluster0.1qzk13u.mongodb.net/?appName=Cluster0"
)

client = MongoClient(_mongo_uri, server_api=ServerApi("1"))
db = client["college"]

# Drop and recreate the collection to clear all data
db["attendancesAIDS"].drop()

attendances_validator = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["Id", "Name", "attendance"],
        "properties": {
            "Id": {"bsonType": "long"},
            "Name": {"bsonType": "string"},
            "attendance": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["date", "status"],
                    "properties": {
                        "date": {"bsonType": "date"},
                        "status": {"enum": ["present", "absent", "late"]},
                        "period": {"bsonType": "int", "minimum": 1, "maximum": 8}
                    }
                }
            }
        }
    }
}

db.command("create", "attendancesAIDS", validator=attendances_validator)
print("✓ AttendancesAIDS collection created with schema validation")

attendances_data = [
    {"Id": 511524243001, "Name": "ABARNA V", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243002, "Name": "ADHISAMMANDHAR R", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243003, "Name": "AKASH D", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243004, "Name": "AKASH J", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243005, "Name": "AKASH R", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243006, "Name": "AKSHARA R", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243007, "Name": "ANU S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243009, "Name": "BAVADHARINI V", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243010, "Name": "DEEPIKA N", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243011, "Name": "DHIYANESHWAR A", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243013, "Name": "ELAKKUVAN S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243015, "Name": "GANESAMOORTHY M", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243016, "Name": "GOKUL N", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243017, "Name": "GOPIKA S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243019, "Name": "GOWTHAM G", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243021, "Name": "HARISHKUMAR G", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243023, "Name": "JANANI M", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243024, "Name": "JANSI S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243025, "Name": "JAYALAKSHMI K", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243026, "Name": "KANIGA H", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243027, "Name": "KARMUGILAN S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243028, "Name": "KAVIYA M", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243029, "Name": "KRISHNARAJ K", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243031, "Name": "LOKESWARAN V", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243032, "Name": "MADHUMITHA K", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243033, "Name": "MAHALAKSHMI B", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243034, "Name": "MURALI S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243035, "Name": "NIRANJANA T N", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243036, "Name": "PARIMALA P", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243037, "Name": "POOVELAN K", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243038, "Name": "PRAKASH D", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243039, "Name": "PRAVEEN KUMAR J", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243040, "Name": "PRIYANGA S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243041, "Name": "PUSHPA N", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243043, "Name": "RAJAGURU M", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243044, "Name": "ROGHU S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243045, "Name": "SABITHA M", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243046, "Name": "SADHA S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243048, "Name": "SELVINKUMAR S S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243049, "Name": "SENTHAMIZHKANNAN S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243050, "Name": "SUPRIYA D", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243052, "Name": "THAMIZHARASAN T", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243053, "Name": "THAMIZH SELVI S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243054, "Name": "THEJASHWINI S G", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243055, "Name": "THIRUMOORTHI A", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243056, "Name": "UDAYA KUMAR K V", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243057, "Name": "VANMATHI S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243058, "Name": "VARUNKUMAR S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243059, "Name": "VIGNESH B", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243060, "Name": "VIJAYASARATHI S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243061, "Name": "VINOTH R", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243062, "Name": "VINOTHINI G V", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
    {"Id": 511524243063, "Name": "RAGHUL S", "attendance": [{"date": datetime(2026, 2, 8), "period": 1, "status": "present"}]},
]

try:
    attendances_collection = db["attendancesAIDS"]
    result = attendances_collection.insert_many(attendances_data)
    print(f"✓ Inserted {len(result.inserted_ids)} attendance records")
    
    print("\n✓ MongoDB setup completed successfully!")
    print(f"\nCollections in database:")
    print(f"  - attendancesAIDS: {db['attendancesAIDS'].count_documents({})}")
    
except Exception as e:
    print(f"✗ Error: {e}")
    print("Make sure MongoDB is running on localhost:27017")

client.close()
