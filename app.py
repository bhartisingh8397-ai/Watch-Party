import os
import uuid
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import db, Video, Room, User, Rating, WatchHistory, ScheduledParty, ContactMessage
from werkzeug.utils import secure_filename
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

load_dotenv()

# For local development, allow insecure transport (HTTP)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'watchparty_secret_key_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///watchparty_v2.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB Limit

# Google OAuth Configuration
app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
app.config['GOOGLE_CLIENT_SECRET'] = os.getenv('GOOGLE_CLIENT_SECRET')

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'flv', 'm4v'}
ALLOWED_SUBTITLE_EXTENSIONS = {'srt', 'vtt', 'ass', 'ssa'}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'}

def allowed_video(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

def allowed_image(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def allowed_subtitle(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_SUBTITLE_EXTENSIONS

def srt_to_vtt(srt_path, vtt_path):
    """Convert .srt subtitle file to .vtt format for browser compatibility."""
    import re
    with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    # Replace SRT time format commas with VTT dots
    content = re.sub(r'(\d{2}:\d{2}:\d{2}),(\d{3})', r'\1.\2', content)
    with open(vtt_path, 'w', encoding='utf-8') as f:
        f.write('WEBVTT\n\n')
        f.write(content)

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Available themes
THEMES = {
    'dark': {'name': 'Midnight Dark', 'icon': '🌙'},
    'gold': {'name': 'Royal Gold', 'icon': '👑'},
    'neon': {'name': 'Neon Cyber', 'icon': '💜'},
    'ocean': {'name': 'Deep Ocean', 'icon': '🌊'},
}

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

def login_required(f):
    """Decorator to require user login for a route."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash('Please login to access this feature.')
            return redirect(url_for('login'))
        if user.is_blocked:
            session.pop('user_id', None)
            flash('Your account has been blocked by the admin.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Simple Admin credentials
ADMIN_PASS = "admin123"

# Initialize DB
with app.app_context():
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Auto-migrate: add missing columns to existing DB
    import sqlite3
    db_path = os.path.join(app.instance_path, 'watchparty_v2.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # User table migrations
        columns = [col[1] for col in cursor.execute("PRAGMA table_info(user)").fetchall()]
        migrations = {
            'google_id': "ALTER TABLE user ADD COLUMN google_id VARCHAR(120)",
            'is_blocked': "ALTER TABLE user ADD COLUMN is_blocked BOOLEAN DEFAULT 0",
            'bio': "ALTER TABLE user ADD COLUMN bio VARCHAR(300) DEFAULT ''",
            'avatar_filename': "ALTER TABLE user ADD COLUMN avatar_filename VARCHAR(500)",
            'theme': "ALTER TABLE user ADD COLUMN theme VARCHAR(20) DEFAULT 'dark'",
        }
        for col_name, sql in migrations.items():
            if col_name not in columns:
                cursor.execute(sql)
                print(f"✅ Migration: Added '{col_name}' to user table")
        
        # Room table migrations
        room_columns = [col[1] for col in cursor.execute("PRAGMA table_info(room)").fetchall()]
        room_migrations = {
            'is_private': "ALTER TABLE room ADD COLUMN is_private BOOLEAN DEFAULT 0",
            'password_hash': "ALTER TABLE room ADD COLUMN password_hash VARCHAR(128)",
        }
        for col_name, sql in room_migrations.items():
            if col_name not in room_columns:
                cursor.execute(sql)
                print(f"✅ Migration: Added '{col_name}' to room table")
        
        # Video table migrations
        video_columns = [col[1] for col in cursor.execute("PRAGMA table_info(video)").fetchall()]
        video_migrations = {
            'genre': "ALTER TABLE video ADD COLUMN genre VARCHAR(100) DEFAULT ''",
            'subtitle_filename': "ALTER TABLE video ADD COLUMN subtitle_filename VARCHAR(500)",
        }
        for col_name, sql in video_migrations.items():
            if col_name not in video_columns:
                cursor.execute(sql)
                print(f"✅ Migration: Added '{col_name}' to video table")
        
        conn.commit()
        conn.close()

# ==================== ROUTES ====================

@app.route('/')
def index():
    rooms = Room.query.all()
    videos = Video.query.all()
    # Get upcoming scheduled parties
    scheduled = ScheduledParty.query.filter(
        ScheduledParty.scheduled_at > datetime.utcnow()
    ).order_by(ScheduledParty.scheduled_at.asc()).limit(5).all()
    return render_template('index.html', rooms=rooms, videos=videos, 
                          user=get_current_user(), scheduled_parties=scheduled)

@app.route('/create_room', methods=['POST'])
@login_required
def create_room():
    room_name = request.form.get('room_name')
    video_id = request.form.get('video_id')
    room_password = request.form.get('room_password', '').strip()
    
    # Check if an active room already exists for this video
    existing_room = Room.query.filter_by(video_id=video_id).first()
    if existing_room:
        return redirect(url_for('room', room_id=existing_room.id))
    
    room_id = str(uuid.uuid4())[:8]
    new_room = Room(id=room_id, name=room_name, video_id=video_id)
    if room_password:
        new_room.set_password(room_password)
    db.session.add(new_room)
    db.session.commit()
    return redirect(url_for('room', room_id=room_id))

@app.route('/room/<room_id>')
@login_required
def room(room_id):
    room_obj = Room.query.get_or_404(room_id)
    
    # If private room, check if user has access
    if room_obj.is_private and not session.get(f'room_access_{room_id}'):
        return redirect(url_for('room_password', room_id=room_id))
    
    # Track watch history
    user = get_current_user()
    if room_obj.video:
        history = WatchHistory(user_id=user.id, video_id=room_obj.video.id)
        db.session.add(history)
        db.session.commit()
    
    # Build subtitle URL if exists
    subtitle_url = None
    if room_obj.video and room_obj.video.subtitle_filename:
        subtitle_url = url_for('static', filename='uploads/' + room_obj.video.subtitle_filename)
    
    return render_template('room.html', room=room_obj, user=user, subtitle_url=subtitle_url)

@app.route('/room/<room_id>/password', methods=['GET', 'POST'])
@login_required
def room_password(room_id):
    room_obj = Room.query.get_or_404(room_id)
    if not room_obj.is_private:
        return redirect(url_for('room', room_id=room_id))
    
    if request.method == 'POST':
        password = request.form.get('password', '')
        if room_obj.check_password(password):
            session[f'room_access_{room_id}'] = True
            return redirect(url_for('room', room_id=room_id))
        flash('Wrong room password!')
    
    return render_template('room_password.html', room=room_obj, user=get_current_user())

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASS:
            session['is_admin'] = True
            return redirect(url_for('admin'))
        flash('Invalid Password')
    return render_template('admin_login.html', user=get_current_user())

@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    flash('Admin logged out successfully!')
    return redirect(url_for('index'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))
        
        session['pending_signup'] = {
            'username': username,
            'password': password
        }
        
        redirect_uri = url_for('authorize_signup_google', _external=True)
        if 'localhost' in redirect_uri:
            redirect_uri = redirect_uri.replace('localhost', '127.0.0.1')
        return google.authorize_redirect(redirect_uri)
    
    return render_template('signup.html', user=get_current_user())

@app.route('/authorize/signup/google')
def authorize_signup_google():
    try:
        if 'error' in request.args:
            session.pop('pending_signup', None)
            flash(f"Google verification failed: {request.args.get('error_description', 'Unknown error')}")
            return redirect(url_for('signup'))
        
        if 'code' not in request.args:
            session.pop('pending_signup', None)
            flash("Authentication code missing.")
            return redirect(url_for('signup'))
        
        pending = session.get('pending_signup')
        if not pending:
            flash('Signup session expired. Please try again.')
            return redirect(url_for('signup'))
        
        token = google.authorize_access_token()
        resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
        user_info = resp.json()
        
        email = user_info.get('email')
        google_id = user_info.get('sub')
        
        if User.query.filter_by(email=email).first():
            session.pop('pending_signup', None)
            flash('This email is already registered. Please login instead.')
            return redirect(url_for('login'))
        
        if User.query.filter_by(username=pending['username']).first():
            session.pop('pending_signup', None)
            flash('Username was taken. Please try again.')
            return redirect(url_for('signup'))
        
        new_user = User(username=pending['username'], email=email, google_id=google_id)
        new_user.set_password(pending['password'])
        db.session.add(new_user)
        db.session.commit()
        
        session.pop('pending_signup', None)
        session['user_id'] = new_user.id
        flash(f'Welcome, {new_user.username}! Your email {email} has been verified ✅')
        return redirect(url_for('index'))
    
    except Exception as e:
        session.pop('pending_signup', None)
        flash(f"Error during email verification: {str(e)}")
        return redirect(url_for('signup'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')
        user = User.query.filter((User.email == identifier) | (User.username == identifier)).first()
        
        if user and user.is_blocked:
            flash('Your account has been blocked by the admin. Contact support.')
            return redirect(url_for('login'))
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Logged in successfully!')
            return redirect(url_for('index'))
        flash('Invalid username/email or password')
    return render_template('login.html', user=get_current_user())

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('is_admin', None)
    flash('Logged out successfully!')
    return redirect(url_for('index'))

@app.route('/login/google')
def login_google():
    redirect_uri = url_for('authorize_google', _external=True)
    if 'localhost' in redirect_uri:
        redirect_uri = redirect_uri.replace('localhost', '127.0.0.1')
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize/google')
def authorize_google():
    try:
        if 'error' in request.args:
            flash(f"Login failed: {request.args.get('error_description', 'Unknown error')}")
            return redirect(url_for('login'))
        if 'code' not in request.args:
            flash("Authentication code missing.")
            return redirect(url_for('login'))
            
        token = google.authorize_access_token()
        resp = google.get('https://openidconnect.googleapis.com/v1/userinfo')
        user_info = resp.json()
        
        email = user_info.get('email')
        google_id = user_info.get('sub')
        username = user_info.get('name', email.split('@')[0])

        user = User.query.filter_by(google_id=google_id).first()
        if not user:
            user = User.query.filter_by(email=email).first()
            if user:
                user.google_id = google_id
            else:
                base_username = username.replace(" ", "").lower()
                unique_username = base_username
                counter = 1
                while User.query.filter_by(username=unique_username).first():
                    unique_username = f"{base_username}{counter}"
                    counter += 1
                user = User(username=unique_username, email=email, google_id=google_id)
                db.session.add(user)
            db.session.commit()

        if user.is_blocked:
            flash('Your account has been blocked by the admin.')
            return redirect(url_for('login'))

        session['user_id'] = user.id
        flash(f'Welcome, {user.username}!')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"An error occurred during Google sign-in: {str(e)}")
        return redirect(url_for('login'))

# ==================== CONTACT & TESTIMONIALS ====================

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()
        
        if name and email and subject and message:
            msg = ContactMessage(name=name, email=email, subject=subject, message=message)
            db.session.add(msg)
            db.session.commit()
            flash('Your message has been sent successfully! We\'ll get back to you soon. ✅')
        else:
            flash('Please fill in all fields.')
        return redirect(url_for('contact'))
    
    # Fetch real user reviews with text for testimonials
    reviews = db.session.query(Rating, User, Video).join(User, Rating.user_id == User.id)\
        .join(Video, Rating.video_id == Video.id)\
        .filter(Rating.review != None, Rating.review != '')\
        .order_by(Rating.created_at.desc()).limit(12).all()
    
    return render_template('contact.html', user=get_current_user(), reviews=reviews)

# ==================== PROFILE ====================

@app.route('/profile/<username>')
@login_required
def profile(username):
    profile_user = User.query.filter_by(username=username).first_or_404()
    watch_history = WatchHistory.query.filter_by(user_id=profile_user.id)\
        .order_by(WatchHistory.watched_at.desc()).limit(20).all()
    user_ratings = Rating.query.filter_by(user_id=profile_user.id)\
        .order_by(Rating.created_at.desc()).all()
    
    # Count unique movies watched
    unique_movies = db.session.query(WatchHistory.video_id)\
        .filter_by(user_id=profile_user.id).distinct().count()
    
    return render_template('profile.html', profile_user=profile_user,
                          watch_history=watch_history, user_ratings=user_ratings,
                          unique_movies=unique_movies, user=get_current_user(),
                          themes=THEMES)

@app.route('/profile/edit', methods=['POST'])
@login_required
def profile_edit():
    user = get_current_user()
    bio = request.form.get('bio', '').strip()[:300]
    user.bio = bio
    
    # Handle avatar upload
    avatar = request.files.get('avatar')
    if avatar and avatar.filename != '' and allowed_image(avatar.filename):
        filename = f"avatar_{user.id}_{secure_filename(avatar.filename)}"
        avatar.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        user.avatar_filename = filename
    
    db.session.commit()
    flash('Profile updated! ✅')
    return redirect(url_for('profile', username=user.username))

@app.route('/profile/theme', methods=['POST'])
@login_required
def set_theme():
    user = get_current_user()
    theme = request.form.get('theme', 'dark')
    if theme in THEMES:
        user.theme = theme
        db.session.commit()
        flash(f'Theme changed to {THEMES[theme]["name"]}! {THEMES[theme]["icon"]}')
    return redirect(url_for('profile', username=user.username))

# ==================== MOVIES & RATINGS ====================

@app.route('/movies')
def movies():
    videos = Video.query.all()
    user = get_current_user()
    
    # Get user's ratings for highlighting
    user_ratings = {}
    if user:
        for r in Rating.query.filter_by(user_id=user.id).all():
            user_ratings[r.video_id] = r.score
    
    return render_template('movies.html', videos=videos, user=user, user_ratings=user_ratings)

@app.route('/movie/<int:video_id>/rate', methods=['POST'])
@login_required
def rate_movie(video_id):
    user = get_current_user()
    video = Video.query.get_or_404(video_id)
    score = int(request.form.get('score', 0))
    review = request.form.get('review', '').strip()[:500]
    
    if score < 1 or score > 5:
        flash('Rating must be between 1 and 5')
        return redirect(url_for('movies'))
    
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
    flash(f'Rated "{video.title}" {"⭐" * score}')
    return redirect(url_for('movies'))

# ==================== RECOMMENDATIONS ====================

@app.route('/recommendations')
@login_required
def recommendations():
    user = get_current_user()
    
    # Get user's watched video IDs
    watched_ids = [wh.video_id for wh in WatchHistory.query.filter_by(user_id=user.id).all()]
    watched_ids = list(set(watched_ids))
    
    # Get user's highly rated video IDs
    liked_ids = [r.video_id for r in Rating.query.filter_by(user_id=user.id).filter(Rating.score >= 4).all()]
    
    # Strategy 1: Find what other users who watched same movies also watched
    similar_user_ids = db.session.query(WatchHistory.user_id)\
        .filter(WatchHistory.video_id.in_(watched_ids))\
        .filter(WatchHistory.user_id != user.id)\
        .distinct().all()
    similar_user_ids = [u[0] for u in similar_user_ids]
    
    recommended_ids = db.session.query(WatchHistory.video_id)\
        .filter(WatchHistory.user_id.in_(similar_user_ids))\
        .filter(~WatchHistory.video_id.in_(watched_ids))\
        .distinct().all()
    recommended_ids = [r[0] for r in recommended_ids]
    
    # Strategy 2: Top rated movies user hasn't watched
    top_rated = db.session.query(Video)\
        .filter(~Video.id.in_(watched_ids))\
        .all()
    top_rated = sorted(top_rated, key=lambda v: v.avg_rating(), reverse=True)
    
    # Combine
    rec_videos = Video.query.filter(Video.id.in_(recommended_ids)).all() if recommended_ids else []
    
    # Add top rated that aren't in rec_videos
    rec_video_ids = [v.id for v in rec_videos]
    for v in top_rated:
        if v.id not in rec_video_ids:
            rec_videos.append(v)
    
    return render_template('movies.html', videos=rec_videos[:12], user=user, 
                          user_ratings={}, is_recommendations=True)

# ==================== SCHEDULED PARTIES ====================

@app.route('/schedule_party', methods=['POST'])
@login_required
def schedule_party():
    user = get_current_user()
    name = request.form.get('party_name')
    video_id = request.form.get('video_id')
    scheduled_str = request.form.get('scheduled_at')
    
    try:
        scheduled_at = datetime.strptime(scheduled_str, '%Y-%m-%dT%H:%M')
    except (ValueError, TypeError):
        flash('Invalid date/time format.')
        return redirect(url_for('index'))
    
    if scheduled_at <= datetime.utcnow():
        flash('Scheduled time must be in the future.')
        return redirect(url_for('index'))
    
    party = ScheduledParty(
        name=name, video_id=video_id,
        creator_id=user.id, scheduled_at=scheduled_at
    )
    db.session.add(party)
    db.session.commit()
    flash(f'Party "{name}" scheduled! 📅')
    return redirect(url_for('index'))

# ==================== ADMIN ====================

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
        
    if request.method == 'POST':
        if 'video' not in request.files:
            flash('No video file part.')
            return redirect(request.url)
            
        video_file = request.files['video']
        poster_file = request.files.get('poster')
        title = request.form.get('title')
        genre = request.form.get('genre', '')
        
        if video_file.filename == '':
            flash('No selected video file.')
            return redirect(request.url)
            
        if video_file and allowed_video(video_file.filename):
            v_filename = secure_filename(video_file.filename)
            v_path = os.path.join(app.config['UPLOAD_FOLDER'], v_filename)
            video_file.save(v_path)
            
            p_filename = None
            if poster_file and poster_file.filename != '' and allowed_image(poster_file.filename):
                p_filename = str(uuid.uuid4())[:8] + "_" + secure_filename(poster_file.filename)
                p_path = os.path.join(app.config['UPLOAD_FOLDER'], p_filename)
                poster_file.save(p_path)
            
            # Handle subtitle upload
            s_filename = None
            subtitle_file = request.files.get('subtitle')
            if subtitle_file and subtitle_file.filename != '' and allowed_subtitle(subtitle_file.filename):
                orig_ext = subtitle_file.filename.rsplit('.', 1)[1].lower()
                s_base = str(uuid.uuid4())[:8] + "_" + secure_filename(subtitle_file.filename)
                s_path = os.path.join(app.config['UPLOAD_FOLDER'], s_base)
                subtitle_file.save(s_path)
                
                # Convert SRT to VTT for browser compatibility
                if orig_ext == 'srt':
                    vtt_name = s_base.rsplit('.', 1)[0] + '.vtt'
                    vtt_path = os.path.join(app.config['UPLOAD_FOLDER'], vtt_name)
                    srt_to_vtt(s_path, vtt_path)
                    s_filename = vtt_name
                else:
                    s_filename = s_base
            
            new_video = Video(title=title, filename=v_filename, poster_filename=p_filename, genre=genre, subtitle_filename=s_filename)
            db.session.add(new_video)
            db.session.commit()
            
            flash('Video uploaded successfully!')
            return redirect(url_for('admin'))
        else:
            flash('Invalid format!')
            return redirect(request.url)

    videos = Video.query.all()
    users = User.query.all()
    
    active_watching = {}
    for room_id, usernames in ROOM_USERS.items():
        room_obj = Room.query.get(room_id)
        if room_obj and room_obj.video:
            for uname in usernames:
                active_watching[uname] = {
                    'movie': room_obj.video.title,
                    'room_id': room_id
                }
    
    # Fetch contact messages for admin
    contact_messages = ContactMessage.query.order_by(ContactMessage.created_at.desc()).all()
    unread_count = ContactMessage.query.filter_by(is_read=False).count()
    
    return render_template('admin.html', videos=videos, users=users, 
                          active_watching=active_watching, user=get_current_user(),
                          contact_messages=contact_messages, unread_count=unread_count)

@app.route('/admin/delete/<int:video_id>', methods=['POST'])
def delete_video(video_id):
    if not session.get('is_admin'):
        flash('Unauthorized Action')
        return redirect(url_for('admin_login'))
        
    video = Video.query.get_or_404(video_id)
    
    try:
        v_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
        if os.path.exists(v_path):
            os.remove(v_path)
        if video.poster_filename:
            p_path = os.path.join(app.config['UPLOAD_FOLDER'], video.poster_filename)
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
    return redirect(url_for('admin'))

@app.route('/admin/block/<int:user_id>', methods=['POST'])
def block_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    user = User.query.get_or_404(user_id)
    user.is_blocked = True
    db.session.commit()
    flash(f"User '{user.username}' has been blocked.")
    return redirect(url_for('admin'))

@app.route('/admin/unblock/<int:user_id>', methods=['POST'])
def unblock_user(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    db.session.commit()
    flash(f"User '{user.username}' has been unblocked.")
    return redirect(url_for('admin'))

@app.route('/admin/message/read/<int:msg_id>', methods=['POST'])
def mark_message_read(msg_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    msg = ContactMessage.query.get_or_404(msg_id)
    msg.is_read = True
    db.session.commit()
    flash('Message marked as read.')
    return redirect(url_for('admin'))

@app.route('/admin/message/delete/<int:msg_id>', methods=['POST'])
def delete_message(msg_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    msg = ContactMessage.query.get_or_404(msg_id)
    db.session.delete(msg)
    db.session.commit()
    flash('Message deleted.')
    return redirect(url_for('admin'))

# ==================== SUBTITLE MANAGEMENT ====================

@app.route('/admin/subtitle/<int:video_id>', methods=['POST'])
def upload_subtitle(video_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    video = Video.query.get_or_404(video_id)
    subtitle_file = request.files.get('subtitle')
    
    if not subtitle_file or subtitle_file.filename == '':
        flash('No subtitle file selected.')
        return redirect(url_for('admin'))
    
    if not allowed_subtitle(subtitle_file.filename):
        flash('Invalid subtitle format. Use .srt, .vtt, .ass, or .ssa')
        return redirect(url_for('admin'))
    
    # Remove old subtitle if exists
    if video.subtitle_filename:
        old_path = os.path.join(app.config['UPLOAD_FOLDER'], video.subtitle_filename)
        if os.path.exists(old_path):
            os.remove(old_path)
    
    orig_ext = subtitle_file.filename.rsplit('.', 1)[1].lower()
    s_base = str(uuid.uuid4())[:8] + "_" + secure_filename(subtitle_file.filename)
    s_path = os.path.join(app.config['UPLOAD_FOLDER'], s_base)
    subtitle_file.save(s_path)
    
    if orig_ext == 'srt':
        vtt_name = s_base.rsplit('.', 1)[0] + '.vtt'
        vtt_path = os.path.join(app.config['UPLOAD_FOLDER'], vtt_name)
        srt_to_vtt(s_path, vtt_path)
        video.subtitle_filename = vtt_name
    else:
        video.subtitle_filename = s_base
    
    db.session.commit()
    flash(f'Subtitle uploaded for "{video.title}" ✅')
    return redirect(url_for('admin'))

@app.route('/admin/subtitle/delete/<int:video_id>', methods=['POST'])
def delete_subtitle(video_id):
    if not session.get('is_admin'):
        return redirect(url_for('admin_login'))
    
    video = Video.query.get_or_404(video_id)
    if video.subtitle_filename:
        s_path = os.path.join(app.config['UPLOAD_FOLDER'], video.subtitle_filename)
        if os.path.exists(s_path):
            os.remove(s_path)
        video.subtitle_filename = None
        db.session.commit()
        flash(f'Subtitle removed from "{video.title}"')
    return redirect(url_for('admin'))

# ==================== NOTIFICATIONS ====================

@app.route('/api/notifications')
@login_required
def get_notifications():
    user = get_current_user()
    notifications = Notification.query.filter_by(user_id=user.id)\
        .order_by(Notification.created_at.desc()).limit(20).all()
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    
    return jsonify({
        'unread_count': unread_count,
        'notifications': [{
            'id': n.id,
            'type': n.type,
            'title': n.title,
            'message': n.message,
            'link': n.link,
            'is_read': n.is_read,
            'created_at': n.created_at.strftime('%d %b • %I:%M %p'),
            'time_ago': _time_ago(n.created_at)
        } for n in notifications]
    })

def _time_ago(dt):
    """Human-friendly time ago string."""
    diff = datetime.utcnow() - dt
    seconds = diff.total_seconds()
    if seconds < 60:
        return 'Just now'
    elif seconds < 3600:
        return f'{int(seconds // 60)}m ago'
    elif seconds < 86400:
        return f'{int(seconds // 3600)}h ago'
    else:
        return f'{int(seconds // 86400)}d ago'

@app.route('/api/notifications/read/<int:notif_id>', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    user = get_current_user()
    notif = Notification.query.filter_by(id=notif_id, user_id=user.id).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    user = get_current_user()
    Notification.query.filter_by(user_id=user.id, is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

# ==================== SOCKET.IO ====================

ROOM_COUNT = {}
SID_TO_ROOM = {}
ROOM_USERS = {}

def broadcast_user_list(room):
    users = list(ROOM_USERS.get(room, set()))
    count = len(users)
    emit('user_count', {'count': count, 'users': users}, room=room)

@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    sid = request.sid
    join_room(room)
    SID_TO_ROOM[sid] = {'room': room, 'username': username}
    if room not in ROOM_USERS:
        ROOM_USERS[room] = set()
    ROOM_USERS[room].add(username)
    broadcast_user_list(room)
    emit('status', {'msg': f'{username} has entered the room.'}, room=room)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    if sid in SID_TO_ROOM:
        info = SID_TO_ROOM[sid]
        room = info['room']
        username = info['username']
        if room in ROOM_USERS:
            ROOM_USERS[room].discard(username)
            if not ROOM_USERS[room]:
                del ROOM_USERS[room]
        broadcast_user_list(room)
        emit('status', {'msg': f'{username} has left the room.'}, room=room)
        del SID_TO_ROOM[sid]

@socketio.on('leave')
def on_leave(data):
    username = data['username']
    room = data['room']
    leave_room(room)
    if room in ROOM_USERS:
        ROOM_USERS[room].discard(username)
        if not ROOM_USERS[room]:
            del ROOM_USERS[room]
    broadcast_user_list(room)
    emit('status', {'msg': f'{username} has left the room.'}, room=room)

@socketio.on('chat_message')
def on_chat_message(data):
    room = data['room']
    username = data['username']
    message = data['message']
    emit('message', {'username': username, 'msg': message}, room=room)

# Typing Indicator
@socketio.on('typing')
def on_typing(data):
    room = data['room']
    username = data['username']
    emit('user_typing', {'username': username}, room=room, include_self=False)

@socketio.on('stop_typing')
def on_stop_typing(data):
    room = data['room']
    username = data['username']
    emit('user_stop_typing', {'username': username}, room=room, include_self=False)

@socketio.on('sync_video')
def on_sync_video(data):
    room = data['room']
    emit('video_event', data, room=room, include_self=False)

@socketio.on('on_screen_text')
def on_screen_text(data):
    room = data['room']
    emit('danmaku', data, room=room)

@socketio.on('reaction')
def on_reaction(data):
    room = data['room']
    emit('reaction_burst', data, room=room)

if __name__ == '__main__':
    socketio.run(app, debug=True)
