from flask import Flask, render_template, request, jsonify
import json
import os
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone

app = Flask(__name__)

DATABASE_PATH = os.environ.get("MG_DATABASE_PATH", "mg_screening_data.sqlite3")
EYE_TRACKING_URL = os.environ.get("EYE_TRACKING_URL", "").strip()
ADMIN_ACCESS_TOKEN = os.environ.get("MG_ADMIN_ACCESS_TOKEN", "").strip()
TRANSFER_VERSION = "mg-screening-transfer-v1"

def init_database():
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                consent_timestamp TEXT NOT NULL,
                name TEXT,
                age TEXT,
                answers_json TEXT NOT NULL,
                medications TEXT,
                results_json TEXT NOT NULL
            )
        """)
        conn.commit()

init_database()

def save_submission(payload, result):
    submission_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.execute(
            """INSERT INTO submissions
               (id, created_at, consent_timestamp, name, age, answers_json, medications, results_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                submission_id, now, payload.get("consentTimestamp") or now,
                payload.get("name", ""), payload.get("age", ""),
                json.dumps(payload.get("answers", {}), ensure_ascii=False),
                payload.get("medications", ""),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
    return submission_id

def admin_authorized():
    supplied = request.headers.get("X-Admin-Token", "")
    return bool(ADMIN_ACCESS_TOKEN) and secrets.compare_digest(supplied, ADMIN_ACCESS_TOKEN)



# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# QUESTION DEFINITIONS
# =========================================================
# q1  - Name              (text, not scored)
# q2  - Age                (text, not scored)
# q3  - Diagnosis of MG           (yes/no -> 10 / 0)
# q4  - Diagnosis of Thymoma      (yes/no -> 10 / 0)
# q5  - Thymectomy                (yes/no -> 10 / 0)
# q6  - Family history of MG      (yes/no -> 10 / 0)
# q7  - Other autoimmune disease  (yes/no -> 10 / 0)
# q8  - Slurring of speech        (yes/no -> severity 1-10 / 0)
# q9  - Trouble eating/chewing/swallowing (yes/no -> severity 1-10 / 0)
# q10 - Shortness of breath       (yes/no -> severity 1-10 / 0)
# q11 - Trouble standing from a chair (yes/no -> severity 1-10 / 0)
# q12 - Diplopia (double vision)  (yes/no -> severity 1-10 / 0)
# q13 - Ptosis (eyelid droop)     (yes/no -> severity 1-10 / 0)
# q14 - Medications               (text, not scored directly)

RISK_QUESTIONS = ["q3", "q4", "q5", "q6", "q7"]

SEVERITY_QUESTIONS = ["q8", "q9", "q10", "q11", "q12", "q13"]

QUESTION_LABELS = {
    "q3": "Diagnosis of MG",
    "q4": "Diagnosis of Thymoma",
    "q5": "Thymectomy",
    "q6": "Family history of MG",
    "q7": "Other autoimmune disease",
    "q8": "Slurring of speech",
    "q9": "Trouble eating, chewing, or swallowing",
    "q10": "Shortness of breath",
    "q11": "Trouble standing up from a chair",
    "q12": "Diplopia (double vision)",
    "q13": "Ptosis (eyelid droop)"
}

MAX_RISK_SCORE = len(RISK_QUESTIONS) * 10          # 50
MAX_SEVERITY_SCORE = len(SEVERITY_QUESTIONS) * 10  # 60
MAX_TOTAL_SCORE = MAX_RISK_SCORE + MAX_SEVERITY_SCORE  # 110


# =========================================================
# SYMPTOM OVERLAP DATABASE
# =========================================================
# A small reference table of other conditions that can
# present with the same symptom, so users understand these
# symptoms are not unique to MG. This is informational only
# and is not a diagnostic tool.

SYMPTOM_DATABASE = {

    "q8": {
        "name": "Slurring of speech",
        "overlapping_conditions": [
            "Stroke / TIA",
            "Bell's palsy",
            "ALS (motor neuron disease)",
            "Multiple sclerosis",
            "Alcohol or sedative intoxication"
        ]
    },

    "q9": {
        "name": "Trouble eating, chewing, or swallowing",
        "overlapping_conditions": [
            "Stroke",
            "ALS (motor neuron disease)",
            "Esophageal stricture or achalasia",
            "Polymyositis / dermatomyositis",
            "Parkinson's disease"
        ]
    },

    "q10": {
        "name": "Shortness of breath",
        "overlapping_conditions": [
            "Asthma",
            "COPD",
            "Anemia",
            "Heart failure",
            "Anxiety / panic disorder"
        ]
    },

    "q11": {
        "name": "Trouble standing up from a chair",
        "overlapping_conditions": [
            "Polymyositis / inflammatory myopathy",
            "Hypothyroidism",
            "Vitamin D deficiency",
            "Lumbar spine or hip disease",
            "General deconditioning"
        ]
    },

    "q12": {
        "name": "Diplopia (double vision)",
        "overlapping_conditions": [
            "Thyroid eye disease (Graves' orbitopathy)",
            "Cranial nerve III/IV/VI palsy",
            "Stroke",
            "Multiple sclerosis",
            "Diabetic neuropathy"
        ]
    },

    "q13": {
        "name": "Ptosis (eyelid droop)",
        "overlapping_conditions": [
            "Horner syndrome",
            "Third cranial nerve palsy",
            "Congenital or age-related ptosis",
            "Chronic progressive external ophthalmoplegia",
            "Levator muscle dehiscence"
        ]
    }

}


# =========================================================
# MEDICATION CAUTION DATABASE
# =========================================================
# Free-text medication answers are scanned for common drug
# names/classes with a known relationship to MG. This is a
# static informational reference, not a live drug database.

MEDICATION_DATABASE = {

    "pyridostigmine": "Standard first-line symptomatic treatment for MG.",
    "mestinon": "Brand name for pyridostigmine, a standard MG treatment.",
    "prednisone": "Commonly used corticosteroid for MG management.",
    "azathioprine": "Steroid-sparing immunosuppressant sometimes used in MG.",
    "mycophenolate": "Steroid-sparing immunosuppressant sometimes used in MG.",

    "ciprofloxacin": "Fluoroquinolone antibiotic — this class has been reported to worsen MG symptoms.",
    "levofloxacin": "Fluoroquinolone antibiotic — this class has been reported to worsen MG symptoms.",
    "moxifloxacin": "Fluoroquinolone antibiotic — this class has been reported to worsen MG symptoms.",

    "gentamicin": "Aminoglycoside antibiotic — this class can impair neuromuscular transmission.",
    "tobramycin": "Aminoglycoside antibiotic — this class can impair neuromuscular transmission.",

    "propranolol": "Beta-blocker — this class can worsen neuromuscular weakness.",
    "metoprolol": "Beta-blocker — this class can worsen neuromuscular weakness.",
    "atenolol": "Beta-blocker — this class can worsen neuromuscular weakness.",

    "magnesium": "Magnesium salts can impair neuromuscular transmission and worsen weakness.",

    "botulinum": "Botulinum toxin directly impairs neuromuscular transmission and is generally avoided in MG."

}


# =========================================================
# SCORING
# =========================================================

def calculate_score(answers):

    risk_score = 0
    severity_score = 0
    breakdown = []
    overlaps = []

    for question in RISK_QUESTIONS:

        response = answers.get(question, {})
        is_yes = response.get("answer") is True

        points = 10 if is_yes else 0
        risk_score += points

        breakdown.append({
            "question": question,
            "label": QUESTION_LABELS[question],
            "answer": "Yes" if is_yes else "No",
            "score": points,
            "max": 10
        })

    for question in SEVERITY_QUESTIONS:

        response = answers.get(question, {})
        is_yes = response.get("answer") is True

        severity = response.get("severity")

        try:
            severity_value = int(severity)
        except (TypeError, ValueError):
            severity_value = 0

        if not is_yes:
            severity_value = 0
        else:
            severity_value = max(1, min(10, severity_value))

        severity_score += severity_value

        breakdown.append({
            "question": question,
            "label": QUESTION_LABELS[question],
            "answer": "Yes" if is_yes else "No",
            "score": severity_value,
            "max": 10
        })

        if is_yes:

            symptom_info = SYMPTOM_DATABASE.get(question)

            if symptom_info:

                overlaps.append({
                    "symptom": symptom_info["name"],
                    "severity": severity_value,
                    "overlapping_conditions": symptom_info["overlapping_conditions"]
                })

    total_score = risk_score + severity_score

    return {
        "riskScore": risk_score,
        "maxRiskScore": MAX_RISK_SCORE,
        "severityScore": severity_score,
        "maxSeverityScore": MAX_SEVERITY_SCORE,
        "totalScore": total_score,
        "maxTotalScore": MAX_TOTAL_SCORE,
        "breakdown": breakdown,
        "overlaps": overlaps
    }


# =========================================================
# LIKELIHOOD GRADING KEY
# =========================================================

def grade_score(total_score):

    if total_score <= 15:

        return {
            "band": "Low",
            "range": "0-15",
            "description":
                "Few reported risk factors or symptoms. "
                "Low apparent likelihood based on this screen alone."
        }

    elif total_score <= 40:

        return {
            "band": "Mild-Moderate",
            "range": "16-40",
            "description":
                "Some risk factors and/or mild symptoms reported. "
                "Consider monitoring and discussing with a clinician."
        }

    elif total_score <= 70:

        return {
            "band": "Moderate-High",
            "range": "41-70",
            "description":
                "Multiple risk factors and/or moderate-severity symptoms "
                "reported. Medical evaluation is reasonable."
        }

    else:

        return {
            "band": "High",
            "range": "71-110",
            "description":
                "Substantial risk factors and/or severe symptoms reported. "
                "Prompt evaluation by a qualified healthcare professional "
                "is recommended."
        }


# =========================================================
# MEDICATION SCANNING
# =========================================================

def scan_medications(medication_text):

    if not isinstance(medication_text, str):
        return []

    text = medication_text.lower()

    matches = []

    for keyword, note in MEDICATION_DATABASE.items():

        if keyword in text:

            matches.append({
                "matched": keyword,
                "note": note
            })

    return matches


# =========================================================
# ANALYSIS API
# =========================================================

@app.route("/api/analyze", methods=["POST"])
def analyze():

    data = request.get_json(silent=True)

    if not data:

        return jsonify({
            "success": False,
            "error": "No questionnaire data was received."
        }), 400

    if data.get("consent") is not True:
        return jsonify({
            "success": False,
            "error": "Consent is required before questionnaire data can be submitted or stored."
        }), 400

    answers = data.get("answers", {})

    name = data.get("name", "")
    age = data.get("age", "")
    medications_text = data.get("medications", "")

    score_results = calculate_score(answers)

    grading = grade_score(score_results["totalScore"])

    medication_matches = scan_medications(medications_text)

    result = {
        "name": name,
        "age": age,
        "scores": score_results,
        "grading": grading,
        "medications": {
            "input": medications_text,
            "matches": medication_matches
        },
        "disclaimer":
            "This questionnaire is a screening prototype for "
            "informational and educational purposes only. It does "
            "not diagnose Myasthenia Gravis, Thymoma, or any other "
            "medical condition, and the scoring/grading key is not "
            "a validated clinical scale. Many of the symptoms and "
            "medication notes above are shared with other conditions "
            "and require professional evaluation to interpret. Always "
            "consult a qualified healthcare professional about new, "
            "persistent, or worsening symptoms, and before starting, "
            "stopping, or changing any medication."
    }

    submission_id = save_submission(data, result)

    transfer_package = {
        "format": TRANSFER_VERSION,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "questionnaire": {
            "name": name,
            "age": age,
            "answers": answers,
            "medications": medications_text,
            "scores": score_results,
            "grading": grading
        }
    }

    return jsonify({
        "success": True,
        **result,
        "submissionId": submission_id,
        "transferPackage": transfer_package,
        "eyeTrackingUrl": EYE_TRACKING_URL,
        "eyeTrackingThreshold": 70
    })


# =========================================================
# PROTECTED RESEARCHER DATA ACCESS
# =========================================================

@app.route("/api/admin/submissions", methods=["GET"])
def admin_submissions():
    if not admin_authorized():
        return jsonify({"success": False, "error": "Unauthorized."}), 401

    with sqlite3.connect(DATABASE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, created_at, consent_timestamp, name, age, answers_json, medications, results_json FROM submissions ORDER BY created_at DESC"
        ).fetchall()

    submissions = []
    for row in rows:
        submissions.append({
            "id": row["id"],
            "createdAt": row["created_at"],
            "consentTimestamp": row["consent_timestamp"],
            "name": row["name"],
            "age": row["age"],
            "answers": json.loads(row["answers_json"]),
            "medications": row["medications"],
            "results": json.loads(row["results_json"])
        })

    return jsonify({"success": True, "count": len(submissions), "submissions": submissions})


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/api/health")
def health():

    return jsonify({
        "status": "running",
        "message": "MG Questionnaire v2 Flask backend is running."
    })


# =========================================================
# ERROR HANDLER
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return jsonify({
        "success": False,
        "error": "The requested page or API endpoint does not exist."
    }), 404


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True
    )
