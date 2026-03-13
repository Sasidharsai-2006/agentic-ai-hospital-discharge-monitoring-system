from datetime import datetime

def analyze_vitals(vitals):
    """
    Strict thresholds:
    SpO2 < 90 → HIGH_RISK
    Temp > 39 → HIGH_RISK
    HR > 120 → HIGH_RISK
    """
    spo2 = vitals.get("spo2")
    temp = vitals.get("temperature")
    hr = vitals.get("heart_rate")
    
    risk_level = "LOW_RISK"
    
    if (spo2 is not None and spo2 < 90) or \
       (temp is not None and temp > 39) or \
       (hr is not None and hr > 120):
        risk_level = "HIGH_RISK"
        
    return risk_level

def detect_critical_alerts(patient_id, vitals):
    """
    Critical conditions:
    SpO2 < 85
    HR > 140
    Temp > 40
    """
    alerts = []
    spo2 = vitals.get("spo2")
    hr = vitals.get("heart_rate")
    temp = vitals.get("temperature")
    
    if spo2 is not None and spo2 < 85:
        alerts.append({
            "patient_id": patient_id,
            "alert_type": "CRITICAL_VITAL",
            "vital": "SpO2",
            "value": spo2,
            "message": "SpO2 dangerously low",
            "timestamp": datetime.now()
        })
    
    if hr is not None and hr > 140:
        alerts.append({
            "patient_id": patient_id,
            "alert_type": "CRITICAL_VITAL",
            "vital": "Heart Rate",
            "value": hr,
            "message": "Heart Rate dangerously high",
            "timestamp": datetime.now()
        })
        
    if temp is not None and temp > 40:
        alerts.append({
            "patient_id": patient_id,
            "alert_type": "CRITICAL_VITAL",
            "vital": "Temperature",
            "value": temp,
            "message": "Temperature dangerously high",
            "timestamp": datetime.now()
        })
        
    return alerts
