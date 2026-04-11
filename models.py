from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=True)
    google_id = db.Column(db.String(120), unique=True, nullable=True)
    is_blocked = db.Column(db.Boolean, default=False)
    bio = db.Column(db.String(300), nullable=True, default="")
    avatar_filename = db.Column(db.String(500), nullable=True)
    theme = db.Column(db.String(20), nullable=True, default="dark")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    ratings = db.relationship("Rating", backref="user", lazy=True)
    watch_history = db.relationship("WatchHistory", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    def avg_given_rating(self):
        if not self.ratings:
            return 0
        return round(sum(r.score for r in self.ratings) / len(self.ratings), 1)


class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(500), nullable=False)
    poster_filename = db.Column(db.String(500), nullable=True)
    genre = db.Column(db.String(100), nullable=True, default="")
    subtitle_filename = db.Column(db.String(500), nullable=True)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    ratings = db.relationship("Rating", backref="video", lazy=True)

    def avg_rating(self):
        if not self.ratings:
            return 0
        return round(sum(r.score for r in self.ratings) / len(self.ratings), 1)

    def rating_count(self):
        return len(self.ratings)


class Room(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    video_id = db.Column(
        db.Integer, db.ForeignKey("video.id"), unique=True, nullable=True
    )
    is_private = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(128), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    video = db.relationship("Video", backref="rooms")

    def set_password(self, password):
        if password:
            self.password_hash = generate_password_hash(password)
            self.is_private = True

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False)  # 1-5
    review = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Prevent duplicate ratings
    __table_args__ = (
        db.UniqueConstraint("user_id", "video_id", name="unique_user_video_rating"),
    )


class WatchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    watched_at = db.Column(db.DateTime, default=datetime.utcnow)

    video = db.relationship("Video")


class ScheduledParty(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey("video.id"), nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    video = db.relationship("Video")
    creator = db.relationship("User")


class ContactMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    subject = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
