# Deterministic risk helpers

def score_density(peak_density, congested_count, emergency_active=False):
    score = min(100.0, peak_density * 78.0 + congested_count * 4.0 + (15.0 if emergency_active else 0.0))
    if score >= 80: level = 'CRITICAL'
    elif score >= 60: level = 'HIGH'
    elif score >= 35: level = 'MODERATE'
    else: level = 'LOW'
    return round(score, 2), level
