"""Profile completion scoring (spec AUTH-09 §11) — computed server-side only."""

# Weighted required-for-application fields; sums to 100.
WEIGHTS = {
    "photo": 15,
    "gender": 10,
    "date_of_birth": 10,
    "nationality_code": 10,
    "education_level": 10,
    "education_field": 5,
    "church_service": 5,
    "confession_father": 5,
    "bio": 10,
    "emergency": 20,  # all three emergency fields together
}


def compute_completion(profile) -> int:
    score = 0
    if profile.photo:
        score += WEIGHTS["photo"]
    for field in ("gender", "date_of_birth", "nationality_code", "education_level",
                  "education_field", "church_service", "confession_father", "bio"):
        if getattr(profile, field):
            score += WEIGHTS[field]
    if profile.emergency_name and profile.emergency_relation and profile.emergency_phone:
        score += WEIGHTS["emergency"]
    return score


def refresh_completion(profile) -> int:
    pct = compute_completion(profile)
    if pct != profile.completion_pct:
        profile.completion_pct = pct
        profile.save(update_fields=["completion_pct", "updated_at"])
    return pct
