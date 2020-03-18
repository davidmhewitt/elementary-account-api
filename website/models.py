import time
from flask_sqlalchemy import SQLAlchemy
from authlib.integrations.sqla_oauth2 import (
    OAuth2ClientMixin,
    OAuth2AuthorizationCodeMixin,
    OAuth2TokenMixin,
)

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True)
    stripe_customer_id = db.Column(db.String(40))

    def __str__(self):
        return self.username

    def get_user_id(self):
        return self.id

class OAuth2Client(db.Model, OAuth2ClientMixin):
    __tablename__ = 'oauth2_client'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')


class OAuth2AuthorizationCode(db.Model, OAuth2AuthorizationCodeMixin):
    __tablename__ = 'oauth2_code'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')


class OAuth2Token(db.Model, OAuth2TokenMixin):
    __tablename__ = 'oauth2_token'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    user = db.relationship('User')

    def is_refresh_token_active(self):
        if self.revoked:
            return False
        expires_at = self.issued_at + self.expires_in * 2
        return expires_at >= time.time()

class Purchase(db.Model):
    __tablename__ = 'purchases'
    app_id = db.Column(db.String, primary_key = True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'))
    until = db.Column(db.DateTime(timezone=True))

    def save_to_db(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def find_purchase(cls, user, app_id):
        return cls.query.filter_by(user_id = user, app_id = app_id).first()

class AnonymousPurchase(db.Model):
    __tablename__ = 'anon_purchases'
    uuid = db.Column(db.String, primary_key = True)
    app_id = db.Column(db.String)

    def save_to_db(self):
        db.session.add(self)
        db.session.commit()

    @classmethod
    def find_purchase(cls, uuid):
        return cls.query.filter_by(uuid = uuid).first()

class Application(db.Model):
    __tablename__ = "applications"
    app_id = db.Column(db.String, primary_key = True, unique = True)
    name = db.Column(db.String)
    stripe_key = db.Column(db.String)
    recommended_amount = db.Column(db.Integer)

    @classmethod
    def find_by_id(cls, id):
        return cls.query.filter_by(app_id = id).first()
