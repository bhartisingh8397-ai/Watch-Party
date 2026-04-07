import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from models import db, Video, Room, User
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'watchparty_secret_key_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///watchparty_v2.db'
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 2GB Limit

ALLOWED_EXTENSIONS = {'mp4', 'mkv', 'avi', 'mov', 'webm', 'wmv', 'flv', 'm4v'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

db.init_app(app)
socketio = SocketIO(app, cors_allowed_origins="*")

def get_current_user():
    user_id = session.get('user_id')
    if user_id:
        return User.query.get(user_id)
    return None

# Simple Admin credentials
ADMIN_PASS = "admin123"

# Initialize DB
with app.app_context():
    db.create_all()
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    rooms = Room.query.all()
    videos = Video.query.all()
    return render_template('index.html', rooms=rooms, videos=videos, user=get_current_user())

@app.route('/create_room', methods=['POST'])
def create_room():
    room_name = request.form.get('room_name')
    video_id = request.form.get('video_id')
    room_id = str(uuid.uuid4())[:8]  # Short room ID
    
    new_room = Room(id=room_id, name=room_name, video_id=video_id)
    db.session.add(new_room)
    db.session.commit()
    return redirect(url_for('room', room_id=room_id))

@app.route('/room/<room_id>')
def room(room_id):
    room_obj = Room.query.get_or_404(room_id)
    return render_template('room.html', room=room_obj, user=get_current_user())

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASS:
            session['is_admin'] = True
            return redirect(url_for('admin'))
        flash('Invalid Password')
    return render_template('admin_login.html', user=get_current_user())

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))
        
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Signup successful! Please login.')
        return redirect(url_for('login'))
    return render_template('signup.html', user=get_current_user())

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            flash('Logged in successfully!')
            return redirect(url_for('index'))
        flash('Invalid username or password')
    return render_template('login.html', user=get_current_user())

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('is_admin', None)
    flash('Logged out successfully!')
    return redirect(url_for('index'))

@app.route('/movies')
def movies():
    videos = Video.query.all()
    # Provide professional default posters for older uploads
    default_poster = "https://images.unsplash.com/photo-1626814026160-2237a95fc5a0?q=80&w=2070&auto=format&fit=crop"
    return render_template('movies.html', videos=videos, default_poster=default_poster, user=get_current_user())

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
        
        if video_file.filename == '':
            flash('No selected video file.')
            return redirect(request.url)
            
        if video_file and allowed_file(video_file.filename):
            # Save Video
            v_filename = secure_filename(video_file.filename)
            v_path = os.path.join(app.config['UPLOAD_FOLDER'], v_filename)
            video_file.save(v_path)
            
            # Save Poster (Optional)
            p_filename = None
            if poster_file and allowed_file(poster_file.filename):
                p_filename = str(uuid.uuid4())[:8] + "_" + secure_filename(poster_file.filename)
                p_path = os.path.join(app.config['UPLOAD_FOLDER'], p_filename)
                poster_file.save(p_path)
            
            new_video = Video(title=title, filename=v_filename, poster_filename=p_filename)
            db.session.add(new_video)
            db.session.commit()
            
            flash('Video and Poster uploaded successfully!')
            return redirect(url_for('admin'))
        else:
            flash('Invalid format! Please upload a valid video.')
            return redirect(request.url)

    videos = Video.query.all()
    return render_template('admin.html', videos=videos, user=get_current_user())

@app.route('/admin/delete/<int:video_id>', methods=['POST'])
def delete_video(video_id):
    if not session.get('is_admin'):
        flash('Unauthorized Action')
        return redirect(url_for('admin_login'))
        
    video = Video.query.get_or_404(video_id)
    
    # 1. Delete Video File
    try:
        v_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
        if os.path.exists(v_path):
            os.remove(v_path)
            
        # 2. Delete Poster File if exists
        if video.poster_filename:
            p_path = os.path.join(app.config['UPLOAD_FOLDER'], video.poster_filename)
            if os.path.exists(p_path):
                os.remove(p_path)
    except Exception as e:
        print(f"Error deleting files: {e}")
        
    # 3. Remove From DB
    db.session.delete(video)
    db.session.commit()
    
    flash(f"Movie '{video.title}' and associated files deleted permanently.")
    return redirect(url_for('admin'))

# SocketIO Room Tracking
ROOM_COUNT = {}
SID_TO_ROOM = {} # Track which SID is in which room for cleanup

@socketio.on('join')
def on_join(data):
    username = data['username']
    room = data['room']
    sid = request.sid
    join_room(room)
    
    # Track SID to Room
    SID_TO_ROOM[sid] = room
    
    # Update count
    ROOM_COUNT[room] = ROOM_COUNT.get(room, 0) + 1
    emit('user_count', {'count': ROOM_COUNT[room]}, room=room)
    
    emit('status', {'msg': f'{username} has entered the room.'}, room=room)

@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    if sid in SID_TO_ROOM:
        room = SID_TO_ROOM[sid]
        
        # Room Cleanup
        if room in ROOM_COUNT:
            ROOM_COUNT[room] = max(0, ROOM_COUNT[room] - 1)
            emit('user_count', {'count': ROOM_COUNT[room]}, room=room)
            
        del SID_TO_ROOM[sid]

@socketio.on('leave')
def on_leave(data):
    username = data['username']
    room = data['room']
    leave_room(room)
    
    # Update count
    ROOM_COUNT[room] = max(0, ROOM_COUNT.get(room, 0) - 1)
    emit('user_count', {'count': ROOM_COUNT[room]}, room=room)
    
    emit('status', {'msg': f'{username} has left the room.'}, room=room)

@socketio.on('chat_message')
def on_chat_message(data):
    room = data['room']
    username = data['username']
    message = data['message']
    emit('message', {'username': username, 'msg': message}, room=room)

@socketio.on('sync_video')
def on_sync_video(data):
    room = data['room']
    # Sync types: play, pause, seek
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
