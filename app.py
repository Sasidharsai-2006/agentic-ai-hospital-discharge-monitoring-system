from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from bson import ObjectId
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import shutil
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

# Database
from database.mongodb import db, patients_col, vitals_col, billing_col, insurance_col, alerts_col, prescriptions_col, payments_col
import hashlib

# Collections
users_col = db.users

# Agents
from agents.risk_agent import analyze_vitals, detect_critical_alerts
from agents.pharmacy_agent import check_medicine_availability, get_medicine_price
from agents.billing_agent import calculate_bill
from agents.insurance_agent import check_insurance_eligibility
from agents.doctor_agent import decide_discharge

# Existing OCR Module
from vital_extractor.extractor import VitalExtractor
from vital_extractor.preprocess import preprocess_image, load_image



app = FastAPI(title="AI Hospital Monitoring System")

# Helper for security
async def verify_admin(request: Request):
    role = request.headers.get("X-Role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

async def verify_patient_exists(patient_id: str):
    p_id = patient_id.lower()
    patient = await patients_col.find_one({"patient_id": p_id})
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files for Frontend
os.makedirs("frontend", exist_ok=True)
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# OCR Extractor Instance
extractor = VitalExtractor()

# Helper for password hashing
def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

@app.on_event("startup")
async def seed_admin():
    admin = await users_col.find_one({"email": "admin@hospital.com"})
    if not admin:
        await users_col.insert_one({
            "email": "admin@hospital.com",
            "password": hash_password("admin123"),
            "role": "admin"
        })
        print("Admin user seeded: admin@hospital.com / admin123")

@app.post("/login")
async def login(email: str = Form(None), password: str = Form(None), patient_id: str = Form(None)):
    if patient_id:
        p_id = patient_id.lower()
        patient = await patients_col.find_one({"patient_id": p_id})
        if not patient:
            raise HTTPException(status_code=404, detail="Patient ID not found")
        return {"role": "patient", "patient_id": p_id, "name": patient['name']}
    
    if email and password:
        user = await users_col.find_one({"email": email, "password": hash_password(password)})
        if not user:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
        return {"role": "admin", "email": email, "token": "admin-session-id"} # Simplified token
        
    raise HTTPException(status_code=400, detail="Missing login credentials")

@app.post("/register_patient")
async def register_patient(
    request: Request,
    name: str = Form(...),
    age: int = Form(...),
    disease: str = Form(...),
    doctor: str = Form(...),
    bed_number: str = Form(...),
):
    await verify_admin(request)
    patient_id = str(uuid.uuid4())[:8]
    patient_data = {
        "patient_id": patient_id,
        "name": name,
        "age": age,
        "disease": disease,
        "doctor": doctor,
        "bed_number": bed_number,
        "status": "admitted",  # Default status
        "admission_date": datetime.now(),
        "bill_paid": False
    }
    await patients_col.insert_one(patient_data)
    return {"message": "Patient registered successfully", "patient_id": patient_id}

@app.post("/upload_vitals")
async def upload_vitals(
    request: Request,
    patient_id: str = Form(...),
    image: UploadFile = File(...)
):
    await verify_admin(request)
    await verify_patient_exists(patient_id)

    os.makedirs("uploads", exist_ok=True)
    file_path = os.path.join("uploads", f"{uuid.uuid4()}_{image.filename}")
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(image.file, buffer)
    
    # OCR Extraction
    try:
        img_bgr = load_image(file_path)
        processed_img = preprocess_image(img_bgr)
        extracted_vitals = extractor.extract_vitals_from_image(processed_img)
        
        # Format vitals for agent and storage
        vitals = {
            "heart_rate": extracted_vitals.get("heart_rate"),
            "spo2": extracted_vitals.get("spo2"),
            "bp": extracted_vitals.get("blood_pressure"),
            "resp_rate": extracted_vitals.get("respiration"),
            "temperature": extracted_vitals.get("temperature"),
        }

        # Risk Agent Analysis
        risk_level = analyze_vitals(vitals)
        
        # Store Vitals
        vitals_data = {
            "patient_id": patient_id,
            "image_path": str(file_path),
            "heart_rate": vitals.get("heart_rate"),
            "spo2": vitals.get("spo2"),
            "bp": vitals.get("bp"),
            "resp_rate": vitals.get("resp_rate"),
            "temperature": vitals.get("temperature"),
            "risk_level": risk_level,
            "timestamp": datetime.now()
        }
        await vitals_col.insert_one(vitals_data)
        
        # Check Critical Alerts
        critical_alerts = detect_critical_alerts(patient_id, vitals)
        if critical_alerts:
            await alerts_col.insert_many(critical_alerts)
        
        return {
            "status": "success",
            "vitals": vitals,
            "risk_level": risk_level,
            "critical_alerts": [a['message'] for a in critical_alerts] if critical_alerts else []
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/assign_medicine")
async def assign_medicine(request: Request, patient_id: str = Form(...), medicine_name: str = Form(...), quantity: int = Form(...)):
    await verify_admin(request)
    p_id = patient_id.lower()
    await verify_patient_exists(p_id)

    availability = check_medicine_availability(medicine_name, quantity)
    if availability == "out_of_stock":
        # Alert doctor agent
        await alerts_col.insert_one({
            "patient_id": p_id,
            "alert_type": "PHARMACY_ALERT",
            "message": f"Medicine {medicine_name} NOT available in pharmacy.",
            "timestamp": datetime.now()
        })
        return {"status": "unavailable", "message": "Medicine not available"}
    
    price = get_medicine_price(medicine_name)
    total_cost = price * quantity
    
    prescription = {
        "patient_id": p_id,
        "medicine_name": medicine_name,
        "quantity": quantity,
        "price": price,
        "total_cost": total_cost,
        "status": "assigned",
        "timestamp": datetime.now()
    }
    await prescriptions_col.insert_one(prescription)
    
    return {"status": "success", "availability": availability, "total_cost": total_cost}

@app.get("/patient/{patient_id}")
async def get_patient(patient_id: str):
    patient = await verify_patient_exists(patient_id)
    # Exclude _id from response
    patient_resp = {k: v for k, v in patient.items() if k != "_id"}
    return patient_resp

@app.get("/vitals/{patient_id}")
async def get_vitals(patient_id: str):
    patient_id = patient_id.lower()
    await verify_patient_exists(patient_id)
    cursor = vitals_col.find({"patient_id": patient_id}, {"_id": 0}).sort("timestamp", -1)
    vitals_list = await cursor.to_list(length=100)
    return vitals_list

@app.get("/billing/{patient_id}")
async def get_billing(patient_id: str):
    patient_id = patient_id.lower()
    # Sum medicine costs
    prescriptions = await prescriptions_col.find({"patient_id": patient_id}).to_list(100)
    medicine_cost = sum(p.get("total_cost", 0) for p in prescriptions)
    
    # Calculate bed days
    patient = await verify_patient_exists(patient_id)
    
    admission_date = patient.get("admission_date") or datetime.now()
    if isinstance(admission_date, str):
        try:
            admission_date = datetime.fromisoformat(admission_date.replace("Z", "+00:00"))
        except:
            admission_date = datetime.now()

    # Ensure both are naive for subtraction
    now = datetime.now()
    if hasattr(admission_date, "tzinfo") and admission_date.tzinfo:
        admission_date = admission_date.replace(tzinfo=None)
    
    days_admitted = max(1, (now - admission_date).days)
    
    # Use dynamic costs if set by admin, else defaults
    bed_cost_per_day = patient.get("bed_cost_per_day", 500)
    treatment_cost = patient.get("treatment_cost", 1000)
    
    bill = calculate_bill(medicine_cost, days_admitted, bed_cost_per_day, treatment_cost)
    
    # Update or insert billing doc
    billing_doc = {
        "medicine_cost": medicine_cost,
        "bed_cost": bill['bed_cost'],
        "treatment_cost": treatment_cost,
        "total_bill": bill['total_bill'],
        "bed_cost_per_day": bed_cost_per_day # Store for record
    }
    
    await billing_col.update_one(
        {"patient_id": patient_id},
        [
            {"$set": billing_doc},
            {"$set": {"bill_paid": {"$ifNull": ["$bill_paid", False]}}}
        ],
        upsert=True
    )
    
    insurance_status = check_insurance_eligibility(patient_id)
    insurance_coverage = 0
    if insurance_status == "approved":
        insurance_coverage = 500  # Mock coverage amount
    
    # Fetch payments
    payments = await payments_col.find({"patient_id": patient_id}).to_list(100)
    paid_amount = sum(p.get("amount", 0) for p in payments)
    
    remaining_balance = max(0, bill['total_bill'] - insurance_coverage - paid_amount)
    
    return {
        "medicine_cost": medicine_cost,
        "bed_cost": bill['bed_cost'],
        "bed_days": days_admitted,
        "bed_rate": bed_cost_per_day,
        "treatment_cost": treatment_cost,
        "total_bill": bill['total_bill'],
        "insurance_coverage": insurance_coverage,
        "paid_amount": paid_amount,
        "remaining_balance": remaining_balance
    }

@app.post("/update_billing_costs")
async def update_billing_costs(request: Request):
    await verify_admin(request)
    data = await request.json()
    patient_id = data.get("patient_id", "").lower()
    field = data.get("field") # 'bed_cost_per_day' or 'treatment_cost'
    new_value = data.get("new_value")
    
    if field not in ["bed_cost_per_day", "treatment_cost"]:
        raise HTTPException(status_code=400, detail="Invalid field")
        
    await patients_col.update_one(
        {"patient_id": patient_id},
        {"$set": {field: float(new_value)}}
    )
    return {"status": "success"}
    
@app.post("/add_payment")
async def add_payment(
    request: Request,
    patient_id: str = Form(...),
    amount: float = Form(...),
    purpose: str = Form(...)
):
    await verify_admin(request)
    patient_id = patient_id.lower()
    await verify_patient_exists(patient_id)
    
    payment_doc = {
        "patient_id": patient_id,
        "amount": amount,
        "purpose": purpose,
        "timestamp": datetime.now()
    }
    await payments_col.insert_one(payment_doc)
    return {"status": "success", "message": "Payment recorded successfully"}

@app.get("/payments/{patient_id}")
async def get_payments(patient_id: str):
    patient_id = patient_id.lower()
    await verify_patient_exists(patient_id)
         
    cursor = payments_col.find({"patient_id": patient_id}, {"_id": 0}).sort("timestamp", -1)
    payments = await cursor.to_list(length=100)
    return payments

@app.get("/decision/{patient_id}")
async def get_decision(patient_id: str):
    patient_id = patient_id.lower()
    # Last 48h vitals
    time_limit = datetime.now() - timedelta(hours=48)
    vitals_history = await vitals_col.find({
        "patient_id": patient_id,
        "timestamp": {"$gte": time_limit}
    }).to_list(100)
    
    latest_vitals = await vitals_col.find_one({"patient_id": patient_id}, sort=[("timestamp", -1)])
    risk_level = analyze_vitals(latest_vitals) if latest_vitals else "UNKNOWN"
    
    billing = await billing_col.find_one({"patient_id": patient_id})
    bill_paid = billing.get("bill_paid", False) if billing else False
    
    discharge, reason = decide_discharge(vitals_history, risk_level, bill_paid)
    
    if discharge:
        await patients_col.update_one({"patient_id": patient_id}, {"$set": {"status": "discharged"}})
        
    return {
        "patient_id": patient_id,
        "discharge": discharge,
        "reason": reason,
        "risk_level": risk_level,
        "bill_paid": bill_paid
    }

@app.get("/patients")
async def get_all_patients():
    patients = await patients_col.find().to_list(100)
    # Convert ObjectIDs to strings
    for p in patients:
        p["_id"] = str(p["_id"])
    return patients

@app.get("/alerts/{patient_id}")
async def get_alerts(patient_id: str):
    patient_id = patient_id.lower()
    await verify_patient_exists(patient_id)
    alerts = await alerts_col.find({"patient_id": patient_id}).sort("timestamp", -1).to_list(50)
    for a in alerts:
        a["_id"] = str(a["_id"])
    return alerts

@app.get("/latest_vitals/{patient_id}")
async def get_latest_vitals(patient_id: str):
    patient_id = patient_id.lower()
    await verify_patient_exists(patient_id)
    latest = await vitals_col.find_one({"patient_id": patient_id}, sort=[("timestamp", -1)])
    if not latest:
        return {}
    latest["_id"] = str(latest["_id"])
    return latest

@app.get("/prescriptions/{patient_id}")
async def get_prescriptions(patient_id: str):
    patient_id = patient_id.lower()
    print(f"DEBUG: Fetching prescriptions for {patient_id}")
    await verify_patient_exists(patient_id)
    cursor = prescriptions_col.find({"patient_id": patient_id}).sort("timestamp", -1)
    prescriptions = await cursor.to_list(length=100)
    print(f"DEBUG: Found {len(prescriptions)} prescriptions")
    for p in prescriptions:
        p["_id"] = str(p["_id"])
    return prescriptions

@app.delete("/prescription/{presc_id}")
async def delete_prescription(request: Request, presc_id: str):
    print(f"DEBUG: DELETE request for {presc_id}")
    print(f"DEBUG: Headers: {request.headers.get('X-Role')}")
    await verify_admin(request)
    try:
        obj_id = ObjectId(presc_id)
        result = await prescriptions_col.delete_one({"_id": obj_id})
        print(f"DEBUG: Deleted count: {result.deleted_count}")
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Prescription not found")
        return {"status": "success", "message": "Prescription deleted"}
    except Exception as e:
        print(f"DEBUG: Delete error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid ID or error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
