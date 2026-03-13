from datetime import datetime, timedelta

def decide_discharge(vitals_history, risk_level, bill_paid):
    """
    Conditions:
    1. Vitals stable for last 48 hours:
       - SpO2 > 94
       - Temp < 38
       - Heart Rate < 100
    2. risk_level = LOW_RISK
    3. bill_paid = true
    """
    # vitals_history is expected to be a list of vital documents from the last 48 hours
    if not vitals_history:
        return False, "No vitals history found for the last 48 hours."

    for v in vitals_history:
        spo2 = v.get("spo2")
        temp = v.get("temperature")
        hr = v.get("heart_rate")
        
        if spo2 is not None and spo2 <= 94:
            return False, f"Unstable SpO2 detected: {spo2}"
        if temp is not None and temp >= 38:
            return False, f"Unstable Temperature detected: {temp}"
        if hr is not None and hr >= 100:
            return False, f"Unstable Heart Rate detected: {hr}"

    if risk_level != "LOW_RISK":
        return False, "Risk level is still HIGH."
    
    if not bill_paid:
        return False, "Hospital bill is not yet paid."

    return True, "Patient is stable and ready for discharge."
