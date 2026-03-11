import sqlite3
import os
import razorpay
import requests
import random
import time
import math

from flask import Flask, render_template, request, redirect, session
from datetime import datetime, timedelta
from math import radians, cos, sin, sqrt, atan2
from twilio.rest import Client

app = Flask(__name__)
app.secret_key = "tutorhub_secret_key"

account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
auth_token = os.environ.get("TWILIO_AUTH_TOKEN")

twilio_client = Client(account_sid, auth_token)

VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID")

razorpay_client = razorpay.Client(
    auth=("rzp_test_SKPN8z2DdFK2Np", "f1nK1fcw6NQj8Ykn6UW1DBjv")
)
# ================= DATABASE =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_db()
    cur = conn.cursor()

    # USERS TABLE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mobile TEXT UNIQUE,
        role TEXT,                 -- student / tutor
        name TEXT,
        subject TEXT,
        mode TEXT,                 -- online / offline
        syllabus TEXT,
        house TEXT,
        city TEXT,
        pincode TEXT,
        latitude REAL,
        longitude REAL,
        is_online INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    # BOOKINGS TABLE (Main Request System)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_mobile TEXT,
        tutor_mobile TEXT,
        subject TEXT,
        booking_date TEXT,
        start_time TEXT,
        end_time TEXT,
        status TEXT DEFAULT 'pending',  -- pending / accepted / completed
        request_time TEXT,
        accepted_time TEXT
    )
    """)

    # STUDENT REQUIREMENTS (Search Tutors)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS requirements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_mobile TEXT,
        subject TEXT,
        class TEXT,
        mode TEXT,
        location TEXT,
        description TEXT,
        created_at TEXT
    )
    """)

    # REVIEWS TABLE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER UNIQUE,
        student_mobile TEXT,
        tutor_mobile TEXT,
        rating INTEGER,
        review TEXT,
        review_date TEXT
    )
    """)

    # PAYMENTS TABLE
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id INTEGER,
        student_mobile TEXT,
        tutor_mobile TEXT,
        amount REAL,
        transaction_id TEXT,
        payment_status TEXT,
        payment_method TEXT,
        payment_date TEXT
    )
    """)

    # TUTOR WITHDRAW REQUEST
    cur.execute("""
    CREATE TABLE IF NOT EXISTS withdraw_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tutor_mobile TEXT,
        amount REAL,
        status TEXT DEFAULT 'Pending',
        request_date TEXT,
        processed_date TEXT
    )
    """)

    conn.commit()
    conn.close()

# ✅ CALL THIS ONCE (OUTSIDE FUNCTION)
create_tables()
# ================= OTP FUNCTION =================
def send_otp(mobile):

    try:
        verification = twilio_client.verify.services(
            VERIFY_SERVICE_SID
        ).verifications.create(
            to="+91" + mobile,
            channel="sms"
        )

        print("OTP sent successfully")
        print("Status:", verification.status)

        return True

    except Exception as e:
        print("OTP Sending Failed:", e)
        return False
# ================= VERIFY OTP =================
def verify_otp(mobile, entered_otp):

    try:
        verification_check = twilio_client.verify.services(
            VERIFY_SERVICE_SID
        ).verification_checks.create(
            to="+91" + mobile,
            code=entered_otp
        )

        if verification_check.status == "approved":
            return True
        else:
            return False

    except Exception as e:
        print("OTP Verification Failed:", e)
        return False
       
# ================= HOME =================
@app.route("/")
def index():
    return render_template("index.html")
# ================= STUDENT REGISTER =================
@app.route("/student-register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":

        name = request.form["name"]
        mobile = request.form["mobile"]
        student_class = request.form["student_class"]
        subject = request.form["subject"]
        mode = request.form["mode"]

        house = request.form["house"]
        city = request.form["city"]
        pincode = request.form["pincode"]

        # Get location
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        # Convert safely
        latitude = float(latitude) if latitude else None
        longitude = float(longitude) if longitude else None

        conn = get_db()

        conn.execute("""
            INSERT OR IGNORE INTO users
            (mobile, role, subject, mode, house, city, pincode, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mobile,
            "student",
            subject,
            mode,
            house,
            city,
            pincode,
            latitude,
            longitude
        ))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("student_register.html")
# ================= TUTOR REGISTER =================
@app.route("/tutor-register", methods=["GET", "POST"])
def tutor_register():

    if request.method == "POST":

        mobile = request.form["mobile"]
        subject = request.form["subjects"]
        mode = request.form["mode"]
        syllabus = request.form["syllabus"]

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")

        latitude = float(latitude) if latitude else None
        longitude = float(longitude) if longitude else None

        conn = get_db()

        conn.execute("""
            INSERT OR IGNORE INTO users
            (mobile, role, subject, mode, syllabus, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            mobile,
            "tutor",
            subject,
            mode,
            syllabus,
            latitude,
            longitude
        ))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("tutor_register.html")
# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        mobile = request.form["mobile"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE mobile=?",
            (mobile,)
        ).fetchone()
        conn.close()

        if not user:
            return "❌ Mobile not registered. Please register first."

        otp = send_otp(mobile)

        # ✅ Set session BEFORE redirect
        session["mobile"] = mobile
        session["role"] = user["role"]
        session["otp"] = str(otp)
        session["otp_time"] = time.time()

        print(f"Session set: {session['mobile']}, OTP: {otp}")  # debug log

        return redirect("/otp")

    return render_template("login.html")
# ================= OTP =================
@app.route("/resend-otp")
def resend_otp():
    if "mobile" not in session:
        return redirect("/login")

    # Resend OTP to same mobile
    otp = send_otp(session["mobile"])
    session["otp"] = str(otp)
    session["otp_time"] = time.time()

    return redirect("/otp")
    @app.route("/otp", methods=["GET", "POST"])
def otp():
    if "mobile" not in session:
        return redirect("/login")

    error = None

    if request.method == "POST":
        entered_otp = request.form["otp"]

        # OTP expiry (5 minutes)
        if time.time() - session.get("otp_time", 0) > 300:
            session.clear()
            return redirect("/login")

        if entered_otp == session.get("otp"):
            session.pop("otp", None)
            session.pop("otp_time", None)

            if session["role"] == "student":
                return redirect("/student-dashboard")
            else:
                return redirect("/tutor-dashboard")

        error = "❌ Wrong OTP. Please try again."

    return render_template("otp.html", error=error)
@app.route("/otp", methods=["GET", "POST"])
def otp():
    # ✅ If session missing, go back to login
    if "mobile" not in session:
        return redirect("/login")

    error = None

    if request.method == "POST":
        entered_otp = request.form["otp"]

        # OTP expiry check (5 minutes)
        if time.time() - session.get("otp_time", 0) > 300:
            session.clear()
            return redirect("/login")

        if entered_otp == session.get("otp"):
            session.pop("otp", None)
            session.pop("otp_time", None)

            if session["role"] == "student":
                return redirect("/student-dashboard")
            else:
                return redirect("/tutor-dashboard")

        error = "❌ Wrong OTP. Try again."

    return render_template("otp.html", error=error)
@app.route("/test-otp")
def test_otp():
    try:
        result = send_otp("YOUR_10_DIGIT_MOBILE")  # put your number
        return f"✅ OTP sent! Check your mobile. OTP={result}"
    except Exception as e:
        return f"❌ Error: {str(e)}"
# ================= STUDENT DASHBOARD =================
@app.route("/student-dashboard")
def student_dashboard():
    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    return render_template("student_dashboard.html")

# ================= TUTOR DASHBOARD =================
@app.route("/tutor-dashboard")
def tutor_dashboard():
    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    tutor_mobile = session["mobile"]
    conn = get_db()

    # ✅ Online Status
    user = conn.execute(
        "SELECT is_online FROM users WHERE mobile=?",
        (tutor_mobile,)
    ).fetchone()

    # ✅ Average Rating & Total Reviews
    rating_data = conn.execute("""
        SELECT 
            IFNULL(AVG(rating), 0) as avg_rating,
            COUNT(*) as total_reviews
        FROM reviews
        WHERE tutor_mobile=?
    """, (tutor_mobile,)).fetchone()

    # ✅ Fetch All Reviews
    reviews = conn.execute("""
        SELECT rating, review, student_mobile
        FROM reviews
        WHERE tutor_mobile=?
        ORDER BY id DESC
    """, (tutor_mobile,)).fetchall()

    # ✅ Total Accepted Sessions
    sessions_data = conn.execute("""
        SELECT COUNT(*) as total_sessions
        FROM bookings
        WHERE tutor_mobile=? AND status='accepted'
    """, (tutor_mobile,)).fetchone()
    # ✅ Pending Tuition Requests
    pending_requests = conn.execute("""
    SELECT COUNT(*) as total
    FROM bookings
    WHERE tutor_mobile=? AND status='pending'
""", (tutor_mobile,)).fetchone()["total"]

    # ✅ Total Earnings (Only Paid Payments)
    earnings_data = conn.execute("""
        SELECT IFNULL(SUM(p.amount), 0) as total_earnings
        FROM payments p
        JOIN bookings b ON p.booking_id = b.id
        WHERE b.tutor_mobile=? AND p.payment_status='Paid'
    """, (tutor_mobile,)).fetchone()

    total_earnings = earnings_data["total_earnings"]

    # ✅ Total Approved Withdrawn Amount
    withdraw_data = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) as withdrawn
        FROM withdraw_requests
        WHERE tutor_mobile=? AND status='Approved'
    """, (tutor_mobile,)).fetchone()

    total_withdrawn = withdraw_data["withdrawn"]

    # ✅ Available Balance
    available_balance = total_earnings - total_withdrawn

    conn.close()

    return render_template(
    "tutor_dashboard.html",
    is_online=user["is_online"] if user else 0,
    avg_rating=round(rating_data["avg_rating"], 1),
    total_reviews=rating_data["total_reviews"],
    total_sessions=sessions_data["total_sessions"],
    total_earnings=total_earnings,
    available_balance=available_balance,
    pending_requests=pending_requests,   # 👈 ADD THIS
    reviews=reviews
)
@app.route("/withdraw", methods=["POST"])
def withdraw():
    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    tutor_mobile = session["mobile"]
    amount = float(request.form["amount"])

    conn = get_db()

    earnings = conn.execute("""
        SELECT IFNULL(SUM(p.amount), 0) as total
        FROM payments p
        JOIN bookings b ON p.booking_id = b.id
        WHERE b.tutor_mobile=? AND p.payment_status='Paid'
    """, (tutor_mobile,)).fetchone()["total"]

    withdrawn = conn.execute("""
        SELECT IFNULL(SUM(amount), 0) as total_withdrawn
        FROM withdraw_requests
        WHERE tutor_mobile=? AND status='Approved'
    """, (tutor_mobile,)).fetchone()["total_withdrawn"]

    available_balance = earnings - withdrawn

    if amount > available_balance:
        conn.close()
        return "❌ Insufficient Balance"

    conn.execute("""
        INSERT INTO withdraw_requests
        (tutor_mobile, amount, request_date)
        VALUES (?, ?, DATE('now'))
    """, (tutor_mobile, amount))

    conn.commit()
    conn.close()

    return redirect("/tutor-dashboard")

@app.route("/check_new_requests")
def check_new_requests():

    if "mobile" not in session or session.get("role") != "tutor":
        return {"new_request": False}

    tutor_mobile = session["mobile"]

    conn = get_db()

    req = conn.execute("""
        SELECT COUNT(*)
        FROM bookings
        WHERE tutor_mobile=? AND status='pending'
    """, (tutor_mobile,)).fetchone()[0]

    conn.close()

    if req > 0:
        return {"new_request": True}
    else:
        return {"new_request": False}
@app.route("/accept-booking/<int:booking_id>")
def accept_booking(booking_id):

    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    conn = get_db()

    conn.execute("""
        UPDATE bookings
        SET status='accepted',
        accepted_time=datetime('now')
        WHERE id=? AND tutor_mobile=?
    """, (booking_id, session["mobile"]))

    conn.commit()
    conn.close()

    return redirect("/tutor-requests")
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

## ================= FIND TUTORS =================
from math import radians, cos, sin, sqrt, atan2

@app.route("/find-tutors", methods=["GET", "POST"])
def find_tutors():

    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    tutors = []

    if request.method == "POST":

        subject = request.form["subject"]
        mode = request.form["mode"]
        syllabus = request.form["syllabus"]

        conn = get_db()

        # Student location
        student = conn.execute("""
            SELECT latitude, longitude
            FROM users
            WHERE mobile=?
        """, (session["mobile"],)).fetchone()

        if not student or student["latitude"] is None or student["longitude"] is None:
            conn.close()
            return "❌ Student location not found"

        student_lat = float(student["latitude"])
        student_lon = float(student["longitude"])

        # Get tutors
        all_tutors = conn.execute("""
            SELECT 
                u.*,
                IFNULL(AVG(r.rating),0) as avg_rating,
                COUNT(r.id) as total_reviews
            FROM users u
            LEFT JOIN reviews r
            ON u.mobile = r.tutor_mobile
            WHERE u.role='tutor'
            AND u.is_online=1
            AND LOWER(u.subject) LIKE LOWER(?)
            AND (u.mode=? OR u.mode='both')
            AND LOWER(u.syllabus)=LOWER(?)
            GROUP BY u.mobile
        """, (f"%{subject}%", mode, syllabus)).fetchall()

        conn.close()

        # Distance calculation
        def calculate_distance(lat1, lon1, lat2, lon2):

            R = 6371

            dlat = radians(lat2 - lat1)
            dlon = radians(lon2 - lon1)

            a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))

            return R * c

        # Filter tutors within 10 km
        for tutor in all_tutors:

            if tutor["latitude"] is not None and tutor["longitude"] is not None:

                tutor_lat = float(tutor["latitude"])
                tutor_lon = float(tutor["longitude"])

                distance = calculate_distance(
                    student_lat,
                    student_lon,
                    tutor_lat,
                    tutor_lon
                )

                if distance <= 10:

                    tutor_dict = dict(tutor)
                    tutor_dict["distance"] = round(distance,2)

                    tutors.append(tutor_dict)

    return render_template("find_tutors.html", tutors=tutors)
# ================= TOGGLE ONLINE =================
@app.route("/toggle-online")
def toggle_online():
    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    conn = get_db()
    conn.execute("""
        UPDATE users
        SET is_online = CASE WHEN is_online=1 THEN 0 ELSE 1 END
        WHERE mobile=?
    """, (session["mobile"],))
    conn.commit()
    conn.close()

    return redirect("/tutor-dashboard")

# ================= BOOK TUTOR =================
from datetime import datetime, timedelta

@app.route("/book-tutor/<tutor_mobile>", methods=["GET", "POST"])
def book_tutor(tutor_mobile):
    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    if request.method == "POST":
        booking_date = request.form["booking_date"]
        start_time = request.form["start_time"]
        end_time = request.form["end_time"]

        conn = get_db()
        tutor = conn.execute(
            "SELECT subject FROM users WHERE mobile=? AND role='tutor'",
            (tutor_mobile,)
        ).fetchone()

        if tutor:
            cursor = conn.cursor()

            cursor.execute("""
    INSERT INTO bookings
    (student_mobile, tutor_mobile, subject, booking_date, start_time, end_time, request_time)
    VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
""", (
    session["mobile"],
    tutor_mobile,
    tutor["subject"],
    booking_date,
    start_time,
    end_time
))

            conn.commit()

            # ✅ GET BOOKING ID
            booking_id = cursor.lastrowid

            conn.close()

            # ✅ REDIRECT TO PAYMENT PAGE
            return redirect(f"/payment/{booking_id}")

        conn.close()

    # -------- SMART TIME SLOTS --------
    now = datetime.now()
    slots = []

    start = now + timedelta(minutes=30)

    minute = 30 if start.minute < 30 else 0
    start = start.replace(minute=minute, second=0)

    for i in range(4):
        end = start + timedelta(hours=1)
        slots.append({
            "start": start.strftime("%H:%M"),
            "end": end.strftime("%H:%M")
        })
        start += timedelta(minutes=30)

    return render_template(
        "book_slot.html",
        tutor_mobile=tutor_mobile,
        slots=slots
    )


# ================= MY BOOKINGS =================
@app.route("/my-bookings")
def my_bookings():
    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    conn = get_db()
    bookings = conn.execute("""
        SELECT * FROM bookings
        WHERE student_mobile=?
        ORDER BY id DESC
    """, (session["mobile"],)).fetchall()
    conn.close()

    return render_template("my_bookings.html", bookings=bookings)
# ================= TUTOR REQUESTS =================
@app.route("/tutor-requests")
def tutor_requests():
    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    conn = get_db()

    # Join bookings with student address details
    requests = conn.execute("""
        SELECT 
            b.id,
            b.student_mobile,
            b.subject,
            b.status,
            b.booking_date,
            b.start_time,
            b.end_time,
            u.house,
            u.city,
            u.pincode
        FROM bookings b
        JOIN users u ON b.student_mobile = u.mobile
        WHERE b.tutor_mobile = ?
        ORDER BY b.id DESC
    """, (session["mobile"],)).fetchall()

    conn.close()

    return render_template("tutor_requests.html", requests=requests)

# ================= UPDATE BOOKING =================
@app.route("/update-booking/<int:booking_id>/<status>")
def update_booking(booking_id, status):
    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    conn = get_db()
    conn.execute("""
        UPDATE bookings
        SET status=?
        WHERE id=? AND tutor_mobile=?
    """, (status, booking_id, session["mobile"]))
    conn.commit()
    conn.close()

    return redirect("/tutor-requests")
# ================= POST REQUIREMENT =================
@app.route("/post-requirement", methods=["GET", "POST"])
def post_requirement():
    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    if request.method == "POST":
        subject = request.form["subject"]
        class_name = request.form["class"]
        mode = request.form["mode"]
        location = request.form["location"]
        description = request.form["description"]

        conn = get_db()
        conn.execute("""
            INSERT INTO requirements 
            (student_mobile, subject, class, mode, location, description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session["mobile"], subject, class_name, mode, location, description))
        conn.commit()
        conn.close()
# ================= ADD REVIEW =================
@app.route("/add-review/<int:booking_id>", methods=["GET", "POST"])
def add_review(booking_id):
    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    conn = get_db()

    # Check booking is accepted
    booking = conn.execute("""
        SELECT * FROM bookings
        WHERE id=? AND student_mobile=? AND status='accepted'
    """, (booking_id, session["mobile"])).fetchone()

    if not booking:
        conn.close()
        return "❌ Review not allowed"

    # Check if already reviewed
    existing_review = conn.execute("""
        SELECT * FROM reviews WHERE booking_id=?
    """, (booking_id,)).fetchone()

    if existing_review:
        conn.close()
        return "⚠ You already submitted a review"

    if request.method == "POST":
        rating = int(request.form["rating"])
        review = request.form["review"]

        if rating < 1 or rating > 5:
            conn.close()
            return "❌ Invalid rating"

        conn.execute("""
            INSERT INTO reviews (booking_id, student_mobile, tutor_mobile, rating, review)
            VALUES (?, ?, ?, ?, ?)
        """, (
            booking_id,
            session["mobile"],
            booking["tutor_mobile"],
            rating,
            review
        ))

        conn.commit()
        conn.close()
        return redirect("/my-bookings")

    conn.close()
    return render_template("add_review.html")
# ================= TUTOR REVIEWS PAGE =================
@app.route("/tutor-reviews")
def tutor_reviews():
    if "mobile" not in session or session.get("role") != "tutor":
        return redirect("/login")

    conn = get_db()

    reviews = conn.execute("""
        SELECT rating, review, student_mobile
        FROM reviews
        WHERE tutor_mobile=?
        ORDER BY id DESC
    """, (session["mobile"],)).fetchall()

    conn.close()

    return render_template("tutor_reviews.html", reviews=reviews)
from datetime import datetime

@app.route("/payment/<int:booking_id>")
def payment(booking_id):

    if "mobile" not in session or session.get("role") != "student":
        return redirect("/login")

    conn = get_db()

    # Get tutor mobile from booking
    booking = conn.execute(
        "SELECT tutor_mobile FROM bookings WHERE id=?",
        (booking_id,)
    ).fetchone()

    tutor_mobile = booking["tutor_mobile"]

    # Get average rating of tutor
    rating_data = conn.execute("""
        SELECT AVG(rating) as avg_rating
        FROM reviews
        WHERE tutor_mobile=?
    """, (tutor_mobile,)).fetchone()

    conn.close()

    avg_rating = rating_data["avg_rating"]

    # If no rating yet
    if avg_rating is None:
        avg_rating = 0

    # 🎯 Pricing Logic
    if avg_rating >= 4.5:
        amount = 300
    elif avg_rating >= 3:
        amount = 200
    else:
        amount = 100

    amount_paise = amount * 100

    order = client.order.create({
        "amount": amount_paise,
        "currency": "INR",
        "payment_capture": 1
    })

    return render_template(
        "razorpay_payment.html",
        order_id=order["id"],
        key_id="rzp_test_SKPN8z2DdFK2Np",
        amount=amount,
        booking_id=booking_id
    )
@app.route("/payment-success/<int:booking_id>")
def payment_success(booking_id):

    if "mobile" not in session:
        return redirect("/login")

    conn = get_db()

    conn.execute("""
        UPDATE bookings
        SET status='pending'
        WHERE id=?
    """, (booking_id,))

    conn.commit()
    conn.close()

    return redirect("/my-bookings")
@app.route("/success")
def success():
    return "<h2>Payment Successful ✅</h2>"
# ================= RUN =================
if __name__ == "__main__":

    app.run(debug=True)





