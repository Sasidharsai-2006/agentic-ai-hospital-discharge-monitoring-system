import motor.motor_asyncio
import os

# --- MONGODB ATLAS CONNECTION ---
# The previous attempt failed with "bad auth". 
# STEP: Replace <db_password> below with your ACTUAL database password.
MONGODB_URI = "mongodb+srv://admin:HospitalSecure123@cluster0.9btwz77.mongodb.net/?appName=Cluster0"

client = motor.motor_asyncio.AsyncIOMotorClient(
    MONGODB_URI,
    serverSelectionTimeoutMS=5000
)
db = client.hospital_monitoring

# Collections
patients_col = db.patients
vitals_col = db.vitals
billing_col = db.billing
insurance_col = db.insurance
alerts_col = db.alerts
prescriptions_col = db.prescriptions
payments_col = db.payments

async def check_db_connection():
    try:
        await client.admin.command('ping')
        return True
    except Exception:
        return False
