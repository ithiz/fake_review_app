from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import sqlite3
import os
import re
import json
from datetime import datetime
import numpy as np

try:
    from scraper import scrape_product_reviews
    SCRAPER_AVAILABLE = True
except ImportError:
    SCRAPER_AVAILABLE = False

app = Flask(__name__)
app.secret_key = "fake_review_detector_secret_2024"
DB_PATH = "fake_reviews.db"

# ─── DATABASE SETUP ─────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            description TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            reviewer_name TEXT,
            review_text TEXT NOT NULL,
            rating INTEGER,
            is_fake INTEGER DEFAULT 0,
            fake_score REAL DEFAULT 0.0,
            flags TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
    """)
    # Seed some sample products if empty
    c.execute("SELECT COUNT(*) FROM products")
    if c.fetchone()[0] == 0:
        products = [
            ("Wireless Bluetooth Headphones", "Electronics", "Premium sound quality headphones with 30hr battery life."),
            ("Vitamin C Supplement 1000mg", "Health", "Daily immune support vitamin C tablets."),
            ("Non-Stick Frying Pan 28cm", "Kitchen", "Heavy-duty non-stick coating, dishwasher safe."),
            ("Running Shoes Pro X", "Sports", "Lightweight running shoes with air cushion sole."),
            ("Face Moisturizer SPF 50", "Beauty", "Daily moisturizer with broad spectrum sun protection."),
        ]
        c.executemany("INSERT INTO products (name, category, description) VALUES (?,?,?)", products)
        # Seed sample reviews (mix of fake and genuine)
        reviews = [
            (1, "John D.", "These headphones are absolutely amazing! Best product ever bought! 5 stars! Will recommend to everyone!! Must buy now!", 5, 1, 0.91, '["Excessive exclamation marks","Repeated superlatives","Hard-sell language"]'),
            (1, "Sarah M.", "Good sound quality but the ear cups feel a bit tight after 2 hours. Battery life is as advertised. Overall decent for the price.", 4, 0, 0.12, '[]'),
            (1, "ReviewBot99", "Perfect product!! Perfect packaging!! Perfect delivery!! I love love love it! No cons no downsides perfect in every way!", 5, 1, 0.95, '["Word repetition","No negatives mentioned","Suspicious username"]'),
            (2, "Alice T.", "Took these for 2 weeks. Noticed my skin looks brighter and I haven't caught a cold yet. Taste is a bit sour but manageable.", 4, 0, 0.08, '[]'),
            (2, "BestBuyer2024", "BEST VITAMINS EVERRR!! Cured all my problems!! Buy now before stock runs out!! Amazing amazing amazing!!!", 5, 1, 0.93, '["Repeated characters","Urgency language","All caps"]'),
            (3, "Mike R.", "Pan works great for eggs and pancakes. The handle gets a bit warm but not dangerously hot. Easy to clean.", 4, 0, 0.07, '[]'),
            (3, "TopReviewer", "Sponsored: This pan exceeded my expectations in every way. Gifted to me but honestly best pan I ever used. Highly recommend!", 5, 1, 0.78, '["Sponsored/gifted disclosure","Unbalanced praise"]'),
            (4, "Emma K.", "Comfortable fit but size runs small. I usually wear 8 but needed an 8.5. Cushioning is excellent for long runs.", 4, 0, 0.11, '[]'),
            (5, "Priya S.", "Love this moisturizer! Skin feels hydrated and the SPF is a bonus. Only complaint is the strong fragrance.", 4, 0, 0.09, '[]'),
        ]
        c.executemany("INSERT INTO reviews (product_id,reviewer_name,review_text,rating,is_fake,fake_score,flags) VALUES (?,?,?,?,?,?,?)", reviews)
    conn.commit()
    conn.close()

# ─── ML DETECTION ENGINE ─────────────────────────────────────────────────────

def analyze_review(text, rating, reviewer_name=""):
    score = 0.0
    flags = []

    lower = text.lower()
    words = lower.split()
    sentences = [s.strip() for s in re.split(r'[.!?]', text) if s.strip()]

    # 1. Excessive punctuation
    excl_count = text.count('!')
    if excl_count >= 3:
        score += 0.15
        flags.append("Excessive exclamation marks")
    elif excl_count >= 2:
        score += 0.07

    # 2. ALL CAPS words
    caps_words = [w for w in text.split() if w.isupper() and len(w) > 2]
    if len(caps_words) >= 3:
        score += 0.12
        flags.append("Excessive all-caps usage")

    # 3. Repeated characters (e.g. "greaaaaat", "loveeee")
    if re.search(r'(.)\1{2,}', text):
        score += 0.10
        flags.append("Repeated characters detected")

    # 4. Superlative overuse
    superlatives = ["best", "greatest", "amazing", "perfect", "excellent", "fantastic",
                    "outstanding", "superb", "brilliant", "incredible", "unbelievable",
                    "phenomenal", "extraordinary", "spectacular", "wonderful"]
    sup_count = sum(1 for w in words if w in superlatives)
    if sup_count >= 4:
        score += 0.18
        flags.append("Repeated superlatives")
    elif sup_count >= 2:
        score += 0.08

    # 5. Hard-sell / urgency language
    if re.search(r'\b(buy now|order now|purchase now|limited stock|don\'t miss|must buy|hurry)\b', lower):
        score += 0.20
        flags.append("Hard-sell / urgency language")

    # 6. Sponsored / gifted disclosure
    if re.search(r'\b(sponsored|gifted|paid|free product|discount code|affiliate)\b', lower):
        score += 0.15
        flags.append("Sponsored/gifted disclosure")

    # 7. Word repetition (same word used 3+ times)
    word_freq = {}
    for w in words:
        if len(w) > 3:
            word_freq[w] = word_freq.get(w, 0) + 1
    repeated = [w for w, c in word_freq.items() if c >= 3]
    if repeated:
        score += 0.12
        flags.append(f"Word repetition: {', '.join(repeated[:3])}")

    # 8. No negatives (for 5-star reviews)
    negative_words = ["but", "however", "although", "except", "issue", "problem",
                      "cons", "downside", "complaint", "disappointing", "bad", "poor"]
    has_negative = any(w in words for w in negative_words)
    if rating == 5 and not has_negative and len(words) > 15:
        score += 0.10
        flags.append("No negatives in 5-star review")

    # 9. Short generic review
    if len(words) < 8 and rating in [1, 5]:
        score += 0.10
        flags.append("Very short extreme review")

    # 10. Suspicious username patterns
    if reviewer_name:
        name_lower = reviewer_name.lower()
        if re.search(r'\d{2,}', reviewer_name):
            score += 0.08
            flags.append("Suspicious username pattern")
        if re.search(r'(reviewer|buyer|customer|user)\d*', name_lower):
            score += 0.08
            flags.append("Generic reviewer name")

    # 11. Rating vs sentiment mismatch
    positive_sentiment = sum(1 for w in words if w in ["good","great","nice","love","excellent","happy","pleased","satisfied"])
    negative_sentiment = sum(1 for w in words if w in ["bad","poor","terrible","awful","worst","hate","broken","disappointed"])
    if rating >= 4 and negative_sentiment > positive_sentiment and negative_sentiment > 2:
        score += 0.15
        flags.append("Rating-sentiment mismatch")
    if rating <= 2 and positive_sentiment > negative_sentiment and positive_sentiment > 2:
        score += 0.15
        flags.append("Rating-sentiment mismatch")

    # Cap score at 1.0
    score = min(score, 1.0)
    is_fake = score >= 0.40

    return {
        "score": round(score, 3),
        "is_fake": is_fake,
        "confidence": round(score * 100, 1),
        "flags": flags,
        "verdict": "FAKE" if is_fake else "GENUINE",
        "risk_level": "High" if score >= 0.70 else ("Medium" if score >= 0.40 else "Low")
    }


# ─── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    conn = get_db()
    products = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()
    stats = conn.execute("""
        SELECT
            COUNT(*) as total_reviews,
            SUM(is_fake) as fake_count,
            COUNT(DISTINCT product_id) as products_reviewed,
            ROUND(AVG(fake_score)*100,1) as avg_risk
        FROM reviews
    """).fetchone()
    conn.close()
    return render_template("index.html", products=products, stats=stats)


@app.route("/analyze", methods=["GET", "POST"])
def analyze():
    products = get_db().execute("SELECT id, name FROM products").fetchall()
    result = None
    form_data = {}
    if request.method == "POST":
        product_id = request.form.get("product_id")
        reviewer_name = request.form.get("reviewer_name", "Anonymous").strip()
        review_text = request.form.get("review_text", "").strip()
        rating = int(request.form.get("rating", 3))
        form_data = {"product_id": product_id, "reviewer_name": reviewer_name,
                     "review_text": review_text, "rating": rating}

        if len(review_text) < 5:
            flash("Review text is too short.", "error")
        else:
            result = analyze_review(review_text, rating, reviewer_name)
            if product_id:
                conn = get_db()
                conn.execute("""
                    INSERT INTO reviews (product_id, reviewer_name, review_text, rating, is_fake, fake_score, flags)
                    VALUES (?,?,?,?,?,?,?)
                """, (product_id, reviewer_name, review_text, rating,
                      int(result["is_fake"]), result["score"], json.dumps(result["flags"])))
                conn.commit()
                conn.close()
                flash("Review analyzed and saved.", "success")

    return render_template("analyze.html", products=products, result=result, form_data=form_data)


@app.route("/products")
def products():
    conn = get_db()
    products = conn.execute("""
        SELECT p.*,
               COUNT(r.id) as review_count,
               ROUND(AVG(r.rating),1) as avg_rating,
               SUM(r.is_fake) as fake_count,
               ROUND(AVG(r.fake_score)*100,1) as avg_risk_score
        FROM products p
        LEFT JOIN reviews r ON r.product_id = p.id
        GROUP BY p.id
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("products.html", products=products)


@app.route("/product/<int:pid>")
def product_detail(pid):
    conn = get_db()
    product = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))
    reviews = conn.execute("""
        SELECT * FROM reviews WHERE product_id=? ORDER BY created_at DESC
    """, (pid,)).fetchall()
    stats = conn.execute("""
        SELECT COUNT(*) as total, SUM(is_fake) as fake_count,
               ROUND(AVG(rating),1) as avg_rating,
               ROUND(AVG(fake_score)*100,1) as avg_risk
        FROM reviews WHERE product_id=?
    """, (pid,)).fetchone()
    conn.close()
    reviews_with_flags = []
    for r in reviews:
        r_dict = dict(r)
        try:
            r_dict["flags_list"] = json.loads(r["flags"] or "[]")
        except:
            r_dict["flags_list"] = []
        reviews_with_flags.append(r_dict)
    return render_template("product_detail.html", product=product, reviews=reviews_with_flags, stats=stats)


@app.route("/add_product", methods=["GET", "POST"])
def add_product():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()
        description = request.form.get("description", "").strip()
        if not name:
            flash("Product name is required.", "error")
        else:
            conn = get_db()
            conn.execute("INSERT INTO products (name,category,description) VALUES (?,?,?)",
                         (name, category, description))
            conn.commit()
            conn.close()
            flash(f"Product '{name}' added successfully!", "success")
            return redirect(url_for("products"))
    return render_template("add_product.html")


@app.route("/reports")
def reports():
    conn = get_db()
    # Top fake reviews
    fake_reviews = conn.execute("""
        SELECT r.*, p.name as product_name
        FROM reviews r JOIN products p ON p.id=r.product_id
        WHERE r.is_fake=1
        ORDER BY r.fake_score DESC LIMIT 20
    """).fetchall()
    # Category risk
    category_stats = conn.execute("""
        SELECT p.category,
               COUNT(r.id) as total,
               SUM(r.is_fake) as fake_count,
               ROUND(AVG(r.fake_score)*100,1) as avg_risk
        FROM reviews r JOIN products p ON p.id=r.product_id
        GROUP BY p.category
    """).fetchall()
    # Overall stats
    overall = conn.execute("""
        SELECT COUNT(*) as total, SUM(is_fake) as fake_count,
               ROUND(100.0*SUM(is_fake)/MAX(COUNT(*),1),1) as fake_pct,
               ROUND(AVG(fake_score)*100,1) as avg_risk
        FROM reviews
    """).fetchone()
    conn.close()
    fake_with_flags = []
    for r in fake_reviews:
        r_dict = dict(r)
        try:
            r_dict["flags_list"] = json.loads(r["flags"] or "[]")
        except:
            r_dict["flags_list"] = []
        fake_with_flags.append(r_dict)
    return render_template("reports.html", fake_reviews=fake_with_flags,
                           category_stats=category_stats, overall=overall)


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json()
    text = data.get("text", "")
    rating = int(data.get("rating", 3))
    name = data.get("reviewer_name", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400
    result = analyze_review(text, rating, name)
    return jsonify(result)


@app.route("/delete_review/<int:rid>", methods=["POST"])
def delete_review(rid):
    conn = get_db()
    review = conn.execute("SELECT product_id FROM reviews WHERE id=?", (rid,)).fetchone()
    conn.execute("DELETE FROM reviews WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    flash("Review deleted.", "success")
    if review:
        return redirect(url_for("product_detail", pid=review["product_id"]))
    return redirect(url_for("reports"))


@app.route("/scrape", methods=["GET", "POST"])
def scrape():
    result = None
    url_input = ""
    scrape_result = None

    if request.method == "POST":
        url_input = request.form.get("product_url", "").strip()

        if not url_input:
            flash("Please enter a product URL.", "error")
        elif not SCRAPER_AVAILABLE:
            flash("Scraper module not available. Make sure scraper.py is present and dependencies are installed.", "error")
        else:
            # Run scraper
            scrape_result = scrape_product_reviews(url_input)

            if scrape_result["success"] and scrape_result["reviews"]:
                # Save product to DB
                conn = get_db()
                cur = conn.execute(
                    "INSERT INTO products (name, category, description) VALUES (?,?,?)",
                    (scrape_result["product_name"],
                     scrape_result["product_category"],
                     f"Scraped from {scrape_result['site'].replace('_',' ').title()} – {url_input[:100]}")
                )
                product_id = cur.lastrowid

                # Run fake detection on each review and save
                analyzed = []
                for rev in scrape_result["reviews"]:
                    detection = analyze_review(
                        rev["review_text"],
                        rev["rating"],
                        rev["reviewer_name"]
                    )
                    conn.execute(
                        "INSERT INTO reviews (product_id, reviewer_name, review_text, rating, is_fake, fake_score, flags) VALUES (?,?,?,?,?,?,?)",
                        (product_id, rev["reviewer_name"], rev["review_text"],
                         rev["rating"], int(detection["is_fake"]),
                         detection["score"], json.dumps(detection["flags"]))
                    )
                    analyzed.append({**rev, **detection})

                conn.commit()
                conn.close()

                fake_count = sum(1 for r in analyzed if r["is_fake"])
                total = len(analyzed)
                fake_pct = round(100 * fake_count / total, 1) if total else 0

                result = {
                    "product_id": product_id,
                    "product_name": scrape_result["product_name"],
                    "site": scrape_result["site"],
                    "total": total,
                    "fake_count": fake_count,
                    "genuine_count": total - fake_count,
                    "fake_pct": fake_pct,
                    "reviews": analyzed,
                    "risk_level": "High" if fake_pct >= 50 else ("Medium" if fake_pct >= 25 else "Low"),
                }
                flash(f"Scraped {total} reviews from {scrape_result['site'].title()}. {fake_count} flagged as fake.", "success")
            else:
                flash(scrape_result.get("error", "Scraping failed. Please try again."), "error")

    return render_template("scrape.html",
                           result=result,
                           url_input=url_input,
                           scrape_result=scrape_result,
                           scraper_available=SCRAPER_AVAILABLE)


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    data = request.get_json()
    url = data.get("url", "")
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    if not SCRAPER_AVAILABLE:
        return jsonify({"error": "Scraper not available"}), 500
    scrape_result = scrape_product_reviews(url)
    if scrape_result["success"]:
        for rev in scrape_result["reviews"]:
            detection = analyze_review(rev["review_text"], rev["rating"], rev["reviewer_name"])
            rev.update(detection)
    return jsonify(scrape_result)


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
