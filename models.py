from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(500), nullable=False)
    poster_filename = db.Column(db.String(500), nullable=True)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

class Room(db.Model):
    id = db.Column(db.String(50), primary_key=True)  # Room code
    name = db.Column(db.String(100), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    video = db.relationship('Video', backref='rooms')
