# FakeShield – Fake Product & Review Detection System
**BCA Project | Koshys Institute of Management Studies**
Student: Devika.B (U19BU23S0135) | Guide: Ms. Greeshma S.S

---

## Tech Stack
| Layer | Technology |
|-------|------------|
| Frontend | HTML5, CSS3, JavaScript |
| Backend | Python 3, Flask |
| Database | SQLite (built-in) |
| ML/NLP | Rule-based scoring engine (11 signal detectors) |
| Libraries | pandas, numpy, scikit-learn |

---

## Project Structure
```
fake_review_app/
├── app.py                  # Flask backend + ML detection engine
├── fake_reviews.db         # SQLite database (auto-created)
├── requirements.txt
├── templates/
│   ├── base.html           # Navigation layout
│   ├── index.html          # Dashboard
│   ├── analyze.html        # Review analysis page
│   ├── products.html       # Product listing
│   ├── product_detail.html # Product + reviews
│   ├── add_product.html    # Add product form
│   └── reports.html        # Fake review reports
└── static/
    ├── css/style.css        # Full stylesheet
    └── js/main.js           # Frontend interactivity
```

---

## Setup & Run

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the app
```bash
python app.py
```

### 3. Open in browser
```
http://localhost:5000
```

The SQLite database is auto-created with sample data on first run.

---

## Features
- **Dashboard** – Overview stats: total reviews, fake count, avg risk score
- **Analyze Review** – Paste any review text to get an instant fake/genuine verdict
- **Live Signals** – Real-time flags appear as you type
- **Products** – Browse products with risk scores
- **Product Detail** – Per-product review list with fake/genuine labels
- **Reports** – Full fake review report with category breakdown
- **Add Product** – Add new products to track

## Detection Signals (11 checks)
1. Excessive exclamation marks (3+)
2. All-caps word overuse
3. Repeated characters (loveeee)
4. Superlative overuse (best, amazing, perfect…)
5. Hard-sell / urgency language (buy now, limited stock…)
6. Sponsored/gifted disclosure
7. Word repetition (same word 3+ times)
8. No negatives in 5-star reviews
9. Very short extreme reviews
10. Suspicious username patterns
11. Rating-sentiment mismatch

Reviews scoring **≥ 40%** are classified as **FAKE**.

---

## API Endpoint
```
POST /api/analyze
Content-Type: application/json

{ "text": "review text here", "rating": 5, "reviewer_name": "User123" }
```
Returns: `{ "score": 0.85, "is_fake": true, "confidence": 85.0, "flags": [...], "verdict": "FAKE", "risk_level": "High" }`
