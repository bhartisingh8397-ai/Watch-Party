import os
import re
import random
import secrets
import time
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    session,
)
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import (
    db,
    Video,
    Room,
    User,
    Rating,
    WatchHistory,
    ScheduledParty,
    ContactMessage,
    Notification,
)
from sqlalchemy import func
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import requests as http_requests

load_dotenv()

APP_ENV = os.getenv("FLASK_ENV", os.getenv("APP_ENV", "development")).lower()
IS_PRODUCTION = APP_ENV == "production"

# Allow insecure OAuth transport only for local development.
if APP_ENV == "development":
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)
secret_key = os.getenv("SECRET_KEY")
if IS_PRODUCTION and not secret_key:
    raise RuntimeError("SECRET_KEY is required in production.")
app.config["SECRET_KEY"] = secret_key or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///watchparty_v2.db"
app.config["UPLOAD_FOLDER"] = os.path.join("static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2GB Limit
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("SESSION_COOKIE_SECURE", "1" if IS_PRODUCTION else "0") == "1"
)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_REFRESH_EACH_REQUEST"] = True
app.config["PREFERRED_URL_SCHEME"] = "https" if IS_PRODUCTION else "http"

if os.getenv("TRUST_PROXY", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Google OAuth Configuration
app.config["GOOGLE_CLIENT_ID"] = os.getenv("GOOGLE_CLIENT_ID")
app.config["GOOGLE_CLIENT_SECRET"] = os.getenv("GOOGLE_CLIENT_SECRET")

# Fast2SMS Configuration
FAST2SMS_API_KEY = os.getenv("FAST2SMS_API_KEY", "")
FAST2SMS_URL = "https://www.fast2sms.com/dev/bulkV2"
OTP_EXPIRY_SECONDS = 300  # 5 minutes
OTP_MAX_REQUESTS = 5  # Max OTP requests per phone per window

oauth = OAuth(app)
google = oauth.register(
    name="google",
    client_id=app.config["GOOGLE_CLIENT_ID"],
    client_secret=app.config["GOOGLE_CLIENT_SECRET"],
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

ALLOWED_VIDEO_EXTENSIONS = {"mp4", "mkv", "avi", "mov", "webm", "wmv", "flv", "m4v"}
ALLOWED_SUBTITLE_EXTENSIONS = {"srt", "vtt", "ass", "ssa"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "svg"}
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")  # Indian mobile numbers
AUTH_RATE_LIMIT_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_ATTEMPTS = 10
ADMIN_LOGIN_MAX_ATTEMPTS = 6
ROOM_PASSWORD_MAX_ATTEMPTS = 10
FAILED_ATTEMPTS = {}


def allowed_video(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS
    )


def allowed_image(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def allowed_subtitle(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_SUBTITLE_EXTENSIONS
    )


def human_file_size(size_bytes):
    """Return a compact human-readable size string."""
    if size_bytes <= 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_idx = 0
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    if unit_idx == 0:
        return f"{int(size)} {units[unit_idx]}"
    return f"{size:.1f} {units[unit_idx]}"


def srt_to_vtt(srt_path, vtt_path):
    """Convert .srt subtitle file to .vtt format for browser compatibility."""
    import re

    with open(srt_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # Replace SRT time format commas with VTT dots
    content = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", content)
    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        f.write(content)


def _clean_old_attempts(now):
    stale_before = now - AUTH_RATE_LIMIT_WINDOW_SECONDS
    for key in list(FAILED_ATTEMPTS.keys()):
        timestamps = [ts for ts in FAILED_ATTEMPTS[key] if ts >= stale_before]
        if timestamps:
            FAILED_ATTEMPTS[key] = timestamps
        else:
            del FAILED_ATTEMPTS[key]


def _rate_limit_key(scope, principal):
    return f"{scope}:{principal}"


def is_rate_limited(scope, principal, max_attempts):
    now = time.time()
    _clean_old_attempts(now)
    key = _rate_limit_key(scope, principal)
    timestamps = FAILED_ATTEMPTS.get(key, [])
    if len(timestamps) < max_attempts:
        return False, 0
    retry_after = int(AUTH_RATE_LIMIT_WINDOW_SECONDS - (now - timestamps[0]))
    return retry_after > 0, max(retry_after, 1)


def record_failed_attempt(scope, principal):
    now = time.time()
    key = _rate_limit_key(scope, principal)
    FAILED_ATTEMPTS.setdefault(key, []).append(now)
    _clean_old_attempts(now)


def clear_failed_attempts(scope, principal):
    FAILED_ATTEMPTS.pop(_rate_limit_key(scope, principal), None)


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def is_strong_password(password):
    """Check password is not empty."""
    return len(password) >= 1


def is_valid_email(email):
    if not email:
        return False
    email = email.strip()
    if len(email) > 254 or ".." in email:
        return False
    return bool(EMAIL_REGEX.fullmatch(email))


def is_valid_phone(phone):
    """Deprecated: Removed phone number validation."""
    return False


def generate_unique_username(name):
    """Generate a unique username from name."""
    base = re.sub(r"[^a-z0-9]", "", name.lower())
    if not base:
        base = "user"
    username = base
    counter = 1
    while User.query.filter(func.lower(User.username) == username).first():
        username = f"{base}{counter}"
        counter += 1
    return username


def _get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": _get_csrf_token}


@app.before_request
def protect_from_csrf():
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return None

    # Skip CSRF for API OTP routes that use JSON
    if request.path in ["/api/send-otp", "/api/verify-otp"]:
        return None

    sent_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    session_token = session.get("csrf_token")
    if not sent_token or not session_token:
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Missing CSRF token"}), 400
        flash("Session validation failed. Please try again.")
        return redirect(request.referrer or url_for("index"))

    if not secrets.compare_digest(sent_token, session_token):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Invalid CSRF token"}), 400
        flash("Session validation failed. Please try again.")
        return redirect(request.referrer or url_for("index"))
    return None


@app.after_request
def apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), payment=()"
    )
    if IS_PRODUCTION and request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Available themes
THEMES = {
    "dark": {"name": "Midnight Dark", "icon": ""},
    "gold": {"name": "Royal Gold", "icon": ""},
    "neon": {"name": "Neon Cyber", "icon": ""},
    "ocean": {"name": "Deep Ocean", "icon": ""},
}


def get_current_user():
    user_id = session.get("user_id")
    if user_id:
        return User.query.get(user_id)
    return None


def login_required(f):
    """Decorator to require user login for a route."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash("Please login to access this feature.")
            return redirect(url_for("login"))
        if user.is_blocked:
            session.pop("user_id", None)
            flash("Your account has been blocked by the admin.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return decorated_function


# Admin credentials
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@watchparty.com")
ADMIN_PASS = os.getenv("ADMIN_PASS")
ADMIN_PASS_HASH = os.getenv("ADMIN_PASS_HASH")
if not IS_PRODUCTION and not ADMIN_PASS and not ADMIN_PASS_HASH:
    ADMIN_PASS = "admin123"
if IS_PRODUCTION and not ADMIN_PASS and not ADMIN_PASS_HASH:
    raise RuntimeError("Set ADMIN_PASS_HASH (recommended) or ADMIN_PASS in production.")


def verify_admin_password(password):
    if ADMIN_PASS_HASH:
        return check_password_hash(ADMIN_PASS_HASH, password or "")
    if ADMIN_PASS:
        return secrets.compare_digest(password or "", ADMIN_PASS)
    return False

# Initialize DB
with app.app_context():
    db.create_all()
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Auto-migrate: add missing columns to existing DB
    import sqlite3

    db_path = os.path.join(app.instance_path, "watchparty_v2.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # User table migrations
        columns = [
            col[1] for col in cursor.execute("PRAGMA table_info(user)").fetchall()
        ]
        migrations = {
            "google_id": "ALTER TABLE user ADD COLUMN google_id VARCHAR(120)",
            "name": "ALTER TABLE user ADD COLUMN name VARCHAR(100)",
            "is_blocked": "ALTER TABLE user ADD COLUMN is_blocked BOOLEAN DEFAULT 0",
            "bio": "ALTER TABLE user ADD COLUMN bio VARCHAR(300) DEFAULT ''",
            "avatar_filename": "ALTER TABLE user ADD COLUMN avatar_filename VARCHAR(500)",
            "theme": "ALTER TABLE user ADD COLUMN theme VARCHAR(20) DEFAULT 'dark'",
            "email_verified": "ALTER TABLE user ADD COLUMN email_verified BOOLEAN DEFAULT 0",
        }
        for col_name, sql in migrations.items():
            if col_name not in columns:
                cursor.execute(sql)
                print(f"Migration: Added '{col_name}' to user table")

        # Room table migrations
        room_columns = [
            col[1] for col in cursor.execute("PRAGMA table_info(room)").fetchall()
        ]
        room_migrations = {
            "is_private": "ALTER TABLE room ADD COLUMN is_private BOOLEAN DEFAULT 0",
            "password_hash": "ALTER TABLE room ADD COLUMN password_hash VARCHAR(128)",
        }
        for col_name, sql in room_migrations.items():
            if col_name not in room_columns:
                cursor.execute(sql)
                print(f"Migration: Added '{col_name}' to room table")

        # Video table migrations
        video_columns = [
            col[1] for col in cursor.execute("PRAGMA table_info(video)").fetchall()
        ]
        video_migrations = {
            "genre": "ALTER TABLE video ADD COLUMN genre VARCHAR(100) DEFAULT ''",
            "subtitle_filename": "ALTER TABLE video ADD COLUMN subtitle_filename VARCHAR(500)",
        }
        for col_name, sql in video_migrations.items():
            if col_name not in video_columns:
                cursor.execute(sql)
                print(f"Migration: Added '{col_name}' to video table")

        conn.commit()
        conn.close()


# ==================== OTP (Email Dummy) ====================

def send_email_otp(email, otp):
    """Sends an OTP via email using Amazon SES SMTP."""
    smtp_server = os.getenv("SMTP_ENDPOINT")
    smtp_port = int(os.getenv("SMTP_PORT", 587))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    sender_email = "honestlyjatin@gmail.com"

    try:
        # Create a multipart/alternative message so email clients can choose their preferred format
        msg = MIMEMultipart("alternative")
        msg['From'] = f"Watch-Party <{sender_email}>"
        msg['To'] = email
        msg['Subject'] = "Your Watch-Party Verification Code"

        text = f"Hello,\n\nYour Watch-Party verification code is: {otp}\n\nThis code is valid for 5 minutes.\n\nThank you!"
        html = f"""\
        <html>
          <head></head>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                <h2 style="color: #2c3e50;">Watch-Party Verification</h2>
                <p>Hello,</p>
                <p>Your verification code is:</p>
                <h1 style="color: #4CAF50; font-size: 32px; letter-spacing: 2px;">{otp}</h1>
                <p>This code is valid for <strong>5 minutes</strong>.</p>
                <br>
                <p style="font-size: 12px; color: #999;">If you didn't request this code, you can safely ignore this email.</p>
            </div>
          </body>
        </html>
        """

        part1 = MIMEText(text, 'plain')
        part2 = MIMEText(html, 'html')

        msg.attach(part1)
        msg.attach(part2)

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)
        server.quit()
        return True, "OTP sent successfully."
    except Exception as e:
        print(f"Failed to send email OTP: {e}")
        return False, "Failed to send OTP email."


@app.route("/api/send-otp", methods=["POST"])
def api_send_otp():
    """Send OTP to email for verification."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Invalid request."}), 400

    email = (data.get("email") or "").strip().lower()

    if not is_valid_email(email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400

    # Rate limit OTP requests
    rate_key = f"otp:{email}"
    limited, retry_after = is_rate_limited("otp", email, OTP_MAX_REQUESTS)
    if limited:
        return jsonify({"success": False, "error": f"Too many OTP requests. Try again in {retry_after} seconds."}), 429

    # Check if email already registered (for signup context)
    context = data.get("context", "signup")
    if context == "signup":
        existing = User.query.filter_by(email=email).first()
        if existing:
            return jsonify({"success": False, "error": "This email is already registered. Please login."}), 400

    # Generate 6-digit OTP
    otp = str(random.randint(100000, 999999))

    # Send OTP
    success, message = send_email_otp(email, otp)

    if success:
        # Store in session
        session["otp_data"] = {
            "otp": otp,
            "email": email,
            "expires_at": time.time() + OTP_EXPIRY_SECONDS,
            "attempts": 0,
        }
        record_failed_attempt("otp", email)  # Track for rate limiting
        return jsonify({"success": True, "message": "OTP sent to your email."})
    else:
        return jsonify({"success": False, "error": message}), 500


@app.route("/api/verify-otp", methods=["POST"])
def api_verify_otp():
    """Verify the OTP entered by user."""
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "error": "Invalid request."}), 400

    otp_entered = (data.get("otp") or "").strip()
    email = (data.get("email") or "").strip().lower()

    otp_data = session.get("otp_data")
    if not otp_data:
        return jsonify({"success": False, "error": "No OTP request found. Please send OTP first."}), 400

    if otp_data["email"] != email:
        return jsonify({"success": False, "error": "Email mismatch."}), 400

    if time.time() > otp_data["expires_at"]:
        session.pop("otp_data", None)
        return jsonify({"success": False, "error": "OTP expired. Please request a new one."}), 400

    # Max 5 verification attempts
    if otp_data.get("attempts", 0) >= 5:
        session.pop("otp_data", None)
        return jsonify({"success": False, "error": "Too many failed attempts. Please request a new OTP."}), 400

    if otp_entered != otp_data["otp"]:
        otp_data["attempts"] = otp_data.get("attempts", 0) + 1
        session["otp_data"] = otp_data
        remaining = 5 - otp_data["attempts"]
        return jsonify({"success": False, "error": f"Incorrect OTP. {remaining} attempts remaining."}), 400

    # OTP verified! Mark in session
    session["email_verified"] = email
    session.pop("otp_data", None)
    return jsonify({"success": True, "message": "Email verified successfully!"})


# ==================== ROUTES ====================


@app.route("/")
def index():
    user = get_current_user()

    # Fetch real user testimonials (ratings with reviews, score >= 4)
    testimonials = (
        Rating.query.filter(Rating.review != "", Rating.score >= 4)
        .order_by(Rating.created_at.desc())
        .limit(6)
        .all()
    )

    if not user:
        # Show landing page for non-logged-in users
        return render_template("landing.html", user=None, testimonials=testimonials)

    # Show dashboard for logged-in users
    rooms = Room.query.all()
    videos = Video.query.all()
    # Get upcoming scheduled parties
    scheduled = (
        ScheduledParty.query.filter(ScheduledParty.scheduled_at > datetime.utcnow())
        .order_by(ScheduledParty.scheduled_at.asc())
        .limit(5)
        .all()
    )
    return render_template(
        "index.html",
        rooms=rooms,
        videos=videos,
        user=user,
        scheduled_parties=scheduled,
    )


@app.route("/create_room", methods=["POST"])
@login_required
def create_room():
    room_name = request.form.get("room_name")
    video_id = request.form.get("video_id")
    room_password = request.form.get("room_password", "").strip()

    # Check if an active room already exists for this video
    existing_room = Room.query.filter_by(video_id=video_id).first()
    if existing_room:
        return redirect(url_for("room", room_id=existing_room.id))

    room_id = str(uuid.uuid4())[:8]
    new_room = Room(id=room_id, name=room_name, video_id=video_id)
    if room_password:
        new_room.set_password(room_password)
    db.session.add(new_room)
    db.session.commit()
    return redirect(url_for("room", room_id=room_id))


@app.route("/room/<room_id>")
@login_required
def room(room_id):
    room_obj = Room.query.get_or_404(room_id)

    # If private room, check if user has access
    if room_obj.is_private and not session.get(f"room_access_{room_id}"):
        return redirect(url_for("room_password", room_id=room_id))

    # Track watch history
    user = get_current_user()
    if room_obj.video:
        history = WatchHistory(user_id=user.id, video_id=room_obj.video.id)
        db.session.add(history)
        db.session.commit()

    # Build subtitle URL if exists
    subtitle_url = None
    if room_obj.video and room_obj.video.subtitle_filename:
        subtitle_url = url_for(
            "static", filename="uploads/" + room_obj.video.subtitle_filename
        )

    return render_template(
        "room.html", room=room_obj, user=user, subtitle_url=subtitle_url
    )


@app.route("/room/<room_id>/password", methods=["GET", "POST"])
@login_required
def room_password(room_id):
    room_obj = Room.query.get_or_404(room_id)
    if not room_obj.is_private:
        return redirect(url_for("room", room_id=room_id))

    if request.method == "POST":
        password = request.form.get("password", "")
        rate_limit_subject = f"{get_client_ip()}:{room_id}"
        limited, retry_after = is_rate_limited(
            "room_password", rate_limit_subject, ROOM_PASSWORD_MAX_ATTEMPTS
        )
        if limited:
            flash(f"Too many attempts. Try again in {retry_after} seconds.")
            return redirect(url_for("room_password", room_id=room_id))

        if room_obj.check_password(password):
            clear_failed_attempts("room_password", rate_limit_subject)
            session[f"room_access_{room_id}"] = True
            return redirect(url_for("room", room_id=room_id))
        record_failed_attempt("room_password", rate_limit_subject)
        flash("Wrong room password!")

    return render_template("room_password.html", room=room_obj, user=get_current_user())


@app.route("/admin_login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        rate_limit_subject = get_client_ip()
        limited, retry_after = is_rate_limited(
            "admin_login", rate_limit_subject, ADMIN_LOGIN_MAX_ATTEMPTS
        )
        if limited:
            flash(f"Too many admin login attempts. Retry in {retry_after} seconds.")
            return render_template("admin_login.html", user=get_current_user())

        if email == ADMIN_EMAIL and verify_admin_password(password):
            clear_failed_attempts("admin_login", rate_limit_subject)
            session.clear()  # Clear any existing user session
            session["is_admin"] = True
            session.permanent = True
            return redirect(url_for("admin"))
        record_failed_attempt("admin_login", rate_limit_subject)
        flash("Invalid Admin Email or Password")
    return render_template("admin_login.html", user=get_current_user())


@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    flash("Admin logged out successfully!")
    return redirect(url_for("index"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not name:
            flash("Please enter your name.")
            return redirect(url_for("signup"))

        if not is_valid_email(email):
            flash("Please enter a valid email address.")
            return redirect(url_for("signup"))

        if not is_strong_password(password):
            flash("Please enter a password.")
            return redirect(url_for("signup"))

        # Check if email was verified via OTP
        verified_email = session.get("email_verified")
        if verified_email != email:
            flash("Please verify your email address with OTP first.")
            return redirect(url_for("signup"))

        # Check if email already registered
        if User.query.filter_by(email=email).first():
            flash("This email is already registered. Please login.")
            return redirect(url_for("login"))

        # Generate unique username
        username = generate_unique_username(name)

        new_user = User(
            username=username,
            name=name,
            email=email,
            email_verified=True,
            password_hash=generate_password_hash(password),
        )
        db.session.add(new_user)
        db.session.commit()

        session.pop("email_verified", None)
        session.pop("otp_data", None)
        session["user_id"] = new_user.id
        session.permanent = True
        flash(f"Welcome, {new_user.name}! Your account has been created.")
        return redirect(url_for("index"))

    return render_template("signup.html", user=get_current_user())


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")
        rate_limit_subject = f"{get_client_ip()}:{identifier.lower()}"
        limited, retry_after = is_rate_limited(
            "login", rate_limit_subject, LOGIN_MAX_ATTEMPTS
        )
        if limited:
            flash(f"Too many login attempts. Retry in {retry_after} seconds.")
            return render_template("login.html", user=get_current_user())

        if not identifier or not password:
            flash("Please enter your credentials.")
            return render_template("login.html", user=get_current_user())

        lowered_identifier = identifier.lower()

        # Search by email or username
        user = User.query.filter(
            (func.lower(User.email) == lowered_identifier)
            | (func.lower(User.username) == lowered_identifier)
        ).first()

        if not user:
            record_failed_attempt("login", rate_limit_subject)
            flash("Invalid credentials. Please check and try again.")
            return render_template("login.html", user=get_current_user())

        if user.is_blocked:
            record_failed_attempt("login", rate_limit_subject)
            flash("Your account has been blocked. Contact support.")
            return redirect(url_for("login"))

        if not user.password_hash and not user.google_id:
            record_failed_attempt("login", rate_limit_subject)
            flash("Account not found. Please sign up.")
            return redirect(url_for("signup"))

        if not user.password_hash:
            record_failed_attempt("login", rate_limit_subject)
            flash("This account uses Google Sign-In. Please continue with Google.")
            return render_template("login.html", user=get_current_user())

        if user.check_password(password):
            clear_failed_attempts("login", rate_limit_subject)
            session.clear()
            session["user_id"] = user.id
            session.permanent = True
            flash("Welcome back!")
            return redirect(url_for("index"))
        record_failed_attempt("login", rate_limit_subject)
        flash("Invalid credentials. Please check and try again.")
    return render_template("login.html", user=get_current_user())


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Logged out successfully!")
    return redirect(url_for("index"))


@app.route("/login/google")
def login_google():
    redirect_uri = url_for("authorize_google", _external=True)
    if "localhost" in redirect_uri:
        redirect_uri = redirect_uri.replace("localhost", "127.0.0.1")
    return google.authorize_redirect(redirect_uri)


@app.route("/authorize/google")
def authorize_google():
    try:
        if "error" in request.args:
            flash(
                f"Login failed: {request.args.get('error_description', 'Unknown error')}"
            )
            return redirect(url_for("login"))
        if "code" not in request.args:
            flash("Authentication code missing.")
            return redirect(url_for("login"))

        token = google.authorize_access_token()
        resp = google.get("https://openidconnect.googleapis.com/v1/userinfo")
        user_info = resp.json()

        email = (user_info.get("email") or "").strip().lower()
        google_id = user_info.get("sub")
        email_verified = bool(user_info.get("email_verified"))
        if not email or not google_id:
            flash("Could not verify your Google account details. Please try again.")
            return redirect(url_for("login"))
        if not is_valid_email(email):
            flash("Invalid email returned by provider.")
            return redirect(url_for("login"))
        if not email_verified:
            flash("Google account email is not verified.")
            return redirect(url_for("login"))
        username = user_info.get("name", email.split("@")[0])

        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User.query.filter(func.lower(User.email) == email).first()
            if user:
                user.google_id = google_id
            else:
                unique_username = generate_unique_username(username)
                user = User(
                    username=unique_username,
                    name=username,
                    email=email,
                    google_id=google_id,
                    password_hash=f"google_oauth_{secrets.token_hex(16)}",
                )
                db.session.add(user)
            db.session.commit()

        if user.is_blocked:
            flash("Your account has been blocked by the admin.")
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        flash(f"Welcome, {user.name or user.username}!")
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"An error occurred during Google sign-in: {str(e)}")
        return redirect(url_for("login"))


# ==================== CONTACT & TESTIMONIALS ====================


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if name and email and subject and message:
            msg = ContactMessage(
                name=name, email=email, subject=subject, message=message
            )
            db.session.add(msg)
            db.session.commit()
            flash(
                "Your message has been sent successfully! We'll get back to you soon."
            )
        else:
            flash("Please fill in all fields.")
        return redirect(url_for("contact"))

    # Fetch real user reviews with text for testimonials
    reviews = (
        db.session.query(Rating, User, Video)
        .join(User, Rating.user_id == User.id)
        .join(Video, Rating.video_id == Video.id)
        .filter(Rating.review != None, Rating.review != "")
        .order_by(Rating.created_at.desc())
        .limit(12)
        .all()
    )

    return render_template("contact.html", user=get_current_user(), reviews=reviews)


# ==================== PROFILE ====================


@app.route("/profile/<username>")
@login_required
def profile(username):
    profile_user = User.query.filter_by(username=username).first_or_404()
    watch_history = (
        WatchHistory.query.filter_by(user_id=profile_user.id)
        .order_by(WatchHistory.watched_at.desc())
        .limit(20)
        .all()
    )
    user_ratings = (
        Rating.query.filter_by(user_id=profile_user.id)
        .order_by(Rating.created_at.desc())
        .all()
    )

    # Count unique movies watched
    unique_movies = (
        db.session.query(WatchHistory.video_id)
        .filter_by(user_id=profile_user.id)
        .distinct()
        .count()
    )

    return render_template(
        "profile.html",
        profile_user=profile_user,
        watch_history=watch_history,
        user_ratings=user_ratings,
        unique_movies=unique_movies,
        user=get_current_user(),
        themes=THEMES,
    )


@app.route("/profile/edit", methods=["POST"])
@login_required
def profile_edit():
    user = get_current_user()
    bio = request.form.get("bio", "").strip()[:300]
    user.bio = bio

    # Handle avatar upload
    avatar = request.files.get("avatar")
    if avatar and avatar.filename != "" and allowed_image(avatar.filename):
        filename = f"avatar_{user.id}_{secure_filename(avatar.filename)}"
        avatar.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        user.avatar_filename = filename

    db.session.commit()
    flash("Profile updated!")
    return redirect(url_for("profile", username=user.username))


@app.route("/profile/theme", methods=["POST"])
@login_required
def set_theme():
    user = get_current_user()
    theme = request.form.get("theme", "dark")
    if theme in THEMES:
        user.theme = theme
        db.session.commit()
        flash(f"Theme changed to {THEMES[theme]['name']}! {THEMES[theme]['icon']}")
    return redirect(url_for("profile", username=user.username))


# ==================== MOVIES & RATINGS ====================


@app.route("/movies")
def movies():
    videos = Video.query.all()
    user = get_current_user()

    # Get user's ratings for highlighting
    user_ratings = {}
    if user:
        for r in Rating.query.filter_by(user_id=user.id).all():
            user_ratings[r.video_id] = r.score

    return render_template(
        "movies.html", videos=videos, user=user, user_ratings=user_ratings
    )


@app.route("/movie/<int:video_id>/rate", methods=["POST"])
@login_required
def rate_movie(video_id):
    user = get_current_user()
    video = Video.query.get_or_404(video_id)
    score = int(request.form.get("score", 0))
    review = request.form.get("review", "").strip()[:500]

    if score < 1 or score > 5:
        flash("Rating must be between 1 and 5")
        return redirect(url_for("movies"))

    # Update or create rating
    existing = Rating.query.filter_by(user_id=user.id, video_id=video_id).first()
    if existing:
        existing.score = score
        existing.review = review
        existing.created_at = datetime.utcnow()
    else:
        rating = Rating(user_id=user.id, video_id=video_id, score=score, review=review)
        db.session.add(rating)

    db.session.commit()
    flash(f'Rated "{video.title}" ({score}/5)')
    return redirect(url_for("movies"))


# ==================== RECOMMENDATIONS ====================


@app.route("/recommendations")
@login_required
def recommendations():
    user = get_current_user()

    # Get user's watched video IDs
    watched_ids = [
        wh.video_id for wh in WatchHistory.query.filter_by(user_id=user.id).all()
    ]
    watched_ids = list(set(watched_ids))

    # Get user's highly rated video IDs
    liked_ids = [
        r.video_id
        for r in Rating.query.filter_by(user_id=user.id).filter(Rating.score >= 4).all()
    ]

    # Strategy 1: Find what other users who watched same movies also watched
    similar_user_ids = (
        db.session.query(WatchHistory.user_id)
        .filter(WatchHistory.video_id.in_(watched_ids))
        .filter(WatchHistory.user_id != user.id)
        .distinct()
        .all()
    )
    similar_user_ids = [u[0] for u in similar_user_ids]

    recommended_ids = (
        db.session.query(WatchHistory.video_id)
        .filter(WatchHistory.user_id.in_(similar_user_ids))
        .filter(~WatchHistory.video_id.in_(watched_ids))
        .distinct()
        .all()
    )
    recommended_ids = [r[0] for r in recommended_ids]

    # Strategy 2: Top rated movies user hasn't watched
    top_rated = db.session.query(Video).filter(~Video.id.in_(watched_ids)).all()
    top_rated = sorted(top_rated, key=lambda v: v.avg_rating(), reverse=True)

    # Combine
    rec_videos = (
        Video.query.filter(Video.id.in_(recommended_ids)).all()
        if recommended_ids
        else []
    )

    # Add top rated that aren't in rec_videos
    rec_video_ids = [v.id for v in rec_videos]
    for v in top_rated:
        if v.id not in rec_video_ids:
            rec_videos.append(v)

    # Get user's ratings for highlighting
    user_ratings = {}
    if user:
        for r in Rating.query.filter_by(user_id=user.id).all():
            user_ratings[r.video_id] = r.score

    return render_template(
        "movies.html",
        videos=rec_videos[:12],
        user=user,
        user_ratings=user_ratings,
        is_recommendations=True,
    )


# ==================== SCHEDULED PARTIES ====================


@app.route("/schedule_party", methods=["POST"])
@login_required
def schedule_party():
    user = get_current_user()
    name = request.form.get("party_name")
    video_id = request.form.get("video_id")
    scheduled_str = request.form.get("scheduled_at")

    try:
        scheduled_at = datetime.strptime(scheduled_str, "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        flash("Invalid date/time format.")
        return redirect(url_for("index"))

    if scheduled_at <= datetime.utcnow():
        flash("Scheduled time must be in the future.")
        return redirect(url_for("index"))

    party = ScheduledParty(
        name=name, video_id=video_id, creator_id=user.id, scheduled_at=scheduled_at
    )
    db.session.add(party)
    db.session.commit()
    flash(f'Party "{name}" scheduled!')
    return redirect(url_for("index"))


# ==================== ADMIN ====================


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        if "video" not in request.files:
            flash("No video file part.")
            return redirect(request.url)

        video_file = request.files["video"]
        poster_file = request.files.get("poster")
        title = request.form.get("title")
        genre = request.form.get("genre", "")

        if video_file.filename == "":
            flash("No selected video file.")
            return redirect(request.url)

        if video_file and allowed_video(video_file.filename):
            v_filename = str(uuid.uuid4())[:8] + "_" + secure_filename(video_file.filename)
            v_path = os.path.join(app.config["UPLOAD_FOLDER"], v_filename)
            video_file.save(v_path)

            p_filename = None
            if (
                poster_file
                and poster_file.filename != ""
                and allowed_image(poster_file.filename)
            ):
                p_filename = (
                    str(uuid.uuid4())[:8] + "_" + secure_filename(poster_file.filename)
                )
                p_path = os.path.join(app.config["UPLOAD_FOLDER"], p_filename)
                poster_file.save(p_path)

            # Handle subtitle upload
            s_filename = None
            subtitle_file = request.files.get("subtitle")
            if (
                subtitle_file
                and subtitle_file.filename != ""
                and allowed_subtitle(subtitle_file.filename)
            ):
                orig_ext = subtitle_file.filename.rsplit(".", 1)[1].lower()
                s_base = (
                    str(uuid.uuid4())[:8]
                    + "_"
                    + secure_filename(subtitle_file.filename)
                )
                s_path = os.path.join(app.config["UPLOAD_FOLDER"], s_base)
                subtitle_file.save(s_path)

                # Convert SRT to VTT for browser compatibility
                if orig_ext == "srt":
                    vtt_name = s_base.rsplit(".", 1)[0] + ".vtt"
                    vtt_path = os.path.join(app.config["UPLOAD_FOLDER"], vtt_name)
                    srt_to_vtt(s_path, vtt_path)
                    s_filename = vtt_name
                else:
                    s_filename = s_base

            new_video = Video(
                title=title,
                filename=v_filename,
                poster_filename=p_filename,
                genre=genre,
                subtitle_filename=s_filename,
            )
            db.session.add(new_video)
            db.session.commit()

            flash("Video uploaded successfully!")
            return redirect(url_for("admin"))
        else:
            flash("Invalid format!")
            return redirect(request.url)

    videos = Video.query.order_by(Video.upload_date.desc()).all()
    users = User.query.all()

    active_watching = {}
    for room_id, usernames in ROOM_USERS.items():
        room_obj = Room.query.get(room_id)
        if room_obj and room_obj.video:
            for uname in usernames:
                active_watching[uname] = {
                    "movie": room_obj.video.title,
                    "room_id": room_id,
                }

    # Fetch contact messages for admin
    contact_messages = ContactMessage.query.order_by(
        ContactMessage.created_at.desc()
    ).all()
    unread_count = ContactMessage.query.filter_by(is_read=False).count()

    total_ratings = Rating.query.count()
    avg_rating_raw = db.session.query(func.avg(Rating.score)).scalar()
    avg_rating = round(float(avg_rating_raw or 0), 1)
    blocked_users = User.query.filter_by(is_blocked=True).count()
    private_rooms = Room.query.filter_by(is_private=True).count()

    video_rows = []
    for video in videos:
        file_size = "Missing file"
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], video.filename)
        if os.path.exists(file_path):
            file_size = human_file_size(os.path.getsize(file_path))
        video_rows.append({"video": video, "file_size": file_size})

    admin_stats = {
        "total_videos": len(videos),
        "private_rooms": private_rooms,
        "total_rooms": Room.query.count(),
        "total_users": len(users),
        "blocked_users": blocked_users,
        "watching_now": len(active_watching),
        "total_ratings": total_ratings,
        "avg_rating": avg_rating,
        "unread_messages": unread_count,
    }

    return render_template(
        "admin.html",
        videos=videos,
        video_rows=video_rows,
        users=users,
        active_watching=active_watching,
        user=get_current_user(),
        contact_messages=contact_messages,
        unread_count=unread_count,
        admin_stats=admin_stats,
    )


@app.route("/admin/delete/<int:video_id>", methods=["POST"])
def delete_video(video_id):
    if not session.get("is_admin"):
        flash("Unauthorized Action")
        return redirect(url_for("admin_login"))

    video = Video.query.get_or_404(video_id)

    try:
        v_path = os.path.join(app.config["UPLOAD_FOLDER"], video.filename)
        if os.path.exists(v_path):
            os.remove(v_path)
        if video.poster_filename:
            p_path = os.path.join(app.config["UPLOAD_FOLDER"], video.poster_filename)
            if os.path.exists(p_path):
                os.remove(p_path)
    except Exception as e:
        print(f"Error deleting files: {e}")

    Room.query.filter_by(video_id=video.id).delete()
    Rating.query.filter_by(video_id=video.id).delete()
    WatchHistory.query.filter_by(video_id=video.id).delete()

    db.session.delete(video)
    db.session.commit()

    flash(f"Movie '{video.title}' deleted permanently.")
    return redirect(url_for("admin"))


@app.route("/admin/block/<int:user_id>", methods=["POST"])
def block_user(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    user = User.query.get_or_404(user_id)
    user.is_blocked = True
    db.session.commit()
    flash(f"User '{user.username}' has been blocked.")
    return redirect(url_for("admin"))


@app.route("/admin/unblock/<int:user_id>", methods=["POST"])
def unblock_user(user_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    db.session.commit()
    flash(f"User '{user.username}' has been unblocked.")
    return redirect(url_for("admin"))


@app.route("/admin/message/read/<int:msg_id>", methods=["POST"])
def mark_message_read(msg_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.is_read = True
    db.session.commit()
    flash("Message marked as read.")
    return redirect(url_for("admin"))


@app.route("/admin/message/delete/<int:msg_id>", methods=["POST"])
def delete_message(msg_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))
    msg = ContactMessage.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash("Message deleted.")
    return redirect(url_for("admin"))


# ==================== SUBTITLE MANAGEMENT ====================


@app.route("/admin/subtitle/<int:video_id>", methods=["POST"])
def upload_subtitle(video_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    video = Video.query.get_or_404(video_id)
    subtitle_file = request.files.get("subtitle")

    if not subtitle_file or subtitle_file.filename == "":
        flash("No subtitle file selected.")
        return redirect(url_for("admin"))

    if not allowed_subtitle(subtitle_file.filename):
        flash("Invalid subtitle format. Use .srt, .vtt, .ass, or .ssa")
        return redirect(url_for("admin"))

    # Remove old subtitle if exists
    if video.subtitle_filename:
        old_path = os.path.join(app.config["UPLOAD_FOLDER"], video.subtitle_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    orig_ext = subtitle_file.filename.rsplit(".", 1)[1].lower()
    s_base = str(uuid.uuid4())[:8] + "_" + secure_filename(subtitle_file.filename)
    s_path = os.path.join(app.config["UPLOAD_FOLDER"], s_base)
    subtitle_file.save(s_path)

    if orig_ext == "srt":
        vtt_name = s_base.rsplit(".", 1)[0] + ".vtt"
        vtt_path = os.path.join(app.config["UPLOAD_FOLDER"], vtt_name)
        srt_to_vtt(s_path, vtt_path)
        video.subtitle_filename = vtt_name
    else:
        video.subtitle_filename = s_base

    db.session.commit()
    flash(f'Subtitle uploaded for "{video.title}"')
    return redirect(url_for("admin"))


@app.route("/admin/subtitle/delete/<int:video_id>", methods=["POST"])
def delete_subtitle(video_id):
    if not session.get("is_admin"):
        return redirect(url_for("admin_login"))

    video = Video.query.get_or_404(video_id)
    if video.subtitle_filename:
        s_path = os.path.join(app.config["UPLOAD_FOLDER"], video.subtitle_filename)
        if os.path.exists(s_path):
            os.remove(s_path)
        video.subtitle_filename = None
        db.session.commit()
        flash(f'Subtitle removed from "{video.title}"')
    return redirect(url_for("admin"))


# ==================== NOTIFICATIONS ====================


@app.route("/api/notifications")
@login_required
def get_notifications():
    user = get_current_user()
    notifications = (
        Notification.query.filter_by(user_id=user.id)
        .order_by(Notification.created_at.desc())
        .limit(20)
        .all()
    )
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()

    return jsonify(
        {
            "unread_count": unread_count,
            "notifications": [
                {
                    "id": n.id,
                    "type": n.type,
                    "title": n.title,
                    "message": n.message,
                    "link": n.link,
                    "is_read": n.is_read,
                    "created_at": n.created_at.strftime("%d %b • %I:%M %p"),
                    "time_ago": _time_ago(n.created_at),
                }
                for n in notifications
            ],
        }
    )


def _time_ago(dt):
    """Human-friendly time ago string."""
    diff = datetime.utcnow() - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return "Just now"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    elif seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    else:
        return f"{int(seconds // 86400)}d ago"


@app.route("/api/notifications/read/<int:notif_id>", methods=["POST"])
@login_required
def mark_notification_read(notif_id):
    user = get_current_user()
    notif = Notification.query.filter_by(id=notif_id, user_id=user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def mark_all_notifications_read():
    user = get_current_user()
    Notification.query.filter_by(user_id=user.id, is_read=False).update(
        {"is_read": True}
    )
    db.session.commit()
    return jsonify({"success": True})


# ==================== SOCKET.IO ====================

SID_TO_ROOM = {}
ROOM_USERS = {}
ROOM_PLAYBACK_STATE = {}


def broadcast_user_list(room):
    usernames = list(ROOM_USERS.get(room, set()))
    user_details = []
    for uname in usernames:
        u = User.query.filter_by(username=uname).first()
        if u:
            user_details.append({
                "username": u.username,
                "avatar": u.avatar_filename
            })
        else:
            user_details.append({
                "username": uname,
                "avatar": None
            })
    emit("user_count", {"count": len(user_details), "users": user_details}, room=room)


def get_room_playback_snapshot(room):
    state = ROOM_PLAYBACK_STATE.get(room)
    if not state:
        return None

    current_time = float(state.get("time", 0))
    if state.get("is_playing"):
        elapsed = max(0.0, time.time() - float(state.get("updated_at", time.time())))
        current_time += elapsed
        event_type = "play"
    else:
        event_type = "pause"

    return {"type": event_type, "time": current_time}


@socketio.on("join")
def on_join(data):
    username = data["username"]
    room = data["room"]
    sid = request.sid
    join_room(room)
    SID_TO_ROOM[sid] = {"room": room, "username": username}
    if room not in ROOM_USERS:
        ROOM_USERS[room] = set()
    ROOM_USERS[room].add(username)
    broadcast_user_list(room)
    emit("status", {"msg": f"{username} has entered the room."}, room=room)
    snapshot = get_room_playback_snapshot(room)
    if snapshot:
        emit("video_state", snapshot, to=sid)


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    if sid in SID_TO_ROOM:
        info = SID_TO_ROOM[sid]
        room = info["room"]
        username = info["username"]
        if room in ROOM_USERS:
            ROOM_USERS[room].discard(username)
            if not ROOM_USERS[room]:
                del ROOM_USERS[room]
                ROOM_PLAYBACK_STATE.pop(room, None)
        broadcast_user_list(room)
        emit("status", {"msg": f"{username} has left the room."}, room=room)
        del SID_TO_ROOM[sid]


@socketio.on("leave")
def on_leave(data):
    username = data["username"]
    room = data["room"]
    leave_room(room)
    if room in ROOM_USERS:
        ROOM_USERS[room].discard(username)
        if not ROOM_USERS[room]:
            del ROOM_USERS[room]
            ROOM_PLAYBACK_STATE.pop(room, None)
    broadcast_user_list(room)
    emit("status", {"msg": f"{username} has left the room."}, room=room)


@socketio.on("chat_message")
def on_chat_message(data):
    room = data["room"]
    username = data["username"]
    message = data["message"]
    
    # Fetch avatar for chat
    user = User.query.filter_by(username=username).first()
    avatar = user.avatar_filename if user else None
    
    emit("message", {"username": username, "msg": message, "avatar": avatar}, room=room)


# Typing Indicator
@socketio.on("typing")
def on_typing(data):
    room = data["room"]
    username = data["username"]
    emit("user_typing", {"username": username}, room=room, include_self=False)


@socketio.on("stop_typing")
def on_stop_typing(data):
    room = data["room"]
    username = data["username"]
    emit("user_stop_typing", {"username": username}, room=room, include_self=False)


@socketio.on("sync_video")
def on_sync_video(data):
    room = data["room"]
    event_type = data.get("type")
    event_time = float(data.get("time", 0))
    current = ROOM_PLAYBACK_STATE.get(room, {"is_playing": False, "time": 0.0})
    if event_type in {"play", "pause", "seek"}:
        if event_type == "play":
            current["is_playing"] = True
            current["time"] = event_time
        elif event_type == "pause":
            current["is_playing"] = False
            current["time"] = event_time
        elif event_type == "seek":
            current["time"] = event_time
        current["updated_at"] = time.time()
        ROOM_PLAYBACK_STATE[room] = current
    emit("video_event", data, room=room, include_self=False)


@socketio.on("request_video_state")
def on_request_video_state(data):
    sid = request.sid
    room = (data or {}).get("room")
    if not room and sid in SID_TO_ROOM:
        room = SID_TO_ROOM[sid].get("room")
    if not room:
        return
    snapshot = get_room_playback_snapshot(room)
    if snapshot:
        emit("video_state", snapshot, to=sid)


@socketio.on("on_screen_text")
def on_screen_text(data):
    room = data["room"]
    emit("danmaku", data, room=room)


@socketio.on("reaction")
def on_reaction(data):
    room = data["room"]
    emit("reaction_burst", data, room=room)


if __name__ == "__main__":
    socketio.run(app, debug=True)



