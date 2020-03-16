import time
import math
from flask import Blueprint, request, session
from flask import render_template, redirect, jsonify
from werkzeug.security import gen_salt
from authlib.integrations.flask_oauth2 import current_token
from authlib.oauth2 import OAuth2Error
from .models import db, User, OAuth2Client
from .oauth2 import authorization, require_oauth
from .stripe import stripe

bp = Blueprint(__name__, 'home')

def current_user():
    if 'id' in session:
        uid = session['id']
        return User.query.get(uid)
    return None


def split_by_crlf(s):
    return [v for v in s.splitlines() if v]


@bp.route('/', methods=('GET', 'POST'))
def home():
    if request.method == 'POST':
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            user = User(username=username)
            db.session.add(user)
            db.session.commit()
        session['id'] = user.id
        return redirect('/')
    user = current_user()
    if user:
        clients = OAuth2Client.query.filter_by(user_id=user.id).all()
    else:
        clients = []
    return render_template('home.html', user=user, clients=clients)


@bp.route('/logout')
def logout():
    del session['id']
    return redirect('/')


@bp.route('/create_client', methods=('GET', 'POST'))
def create_client():
    user = current_user()
    if not user:
        return redirect('/')
    if request.method == 'GET':
        return render_template('create_client.html')

    client_id = gen_salt(24)
    client_id_issued_at = int(time.time())
    client = OAuth2Client(
        client_id=client_id,
        client_id_issued_at=client_id_issued_at,
        user_id=user.id,
    )

    if client.token_endpoint_auth_method == 'none':
        client.client_secret = ''
    else:
        client.client_secret = gen_salt(48)

    form = request.form
    client_metadata = {
        "client_name": form["client_name"],
        "client_uri": form["client_uri"],
        "grant_types": split_by_crlf(form["grant_type"]),
        "redirect_uris": split_by_crlf(form["redirect_uri"]),
        "response_types": split_by_crlf(form["response_type"]),
        "scope": form["scope"],
        "token_endpoint_auth_method": form["token_endpoint_auth_method"]
    }
    client.set_client_metadata(client_metadata)
    db.session.add(client)
    db.session.commit()
    return redirect('/')


@bp.route('/oauth/authorize', methods=['GET', 'POST'])
def authorize():
    user = current_user()
    if request.method == 'GET':
        try:
            grant = authorization.validate_consent_request(end_user=user)
        except OAuth2Error as error:
            return error.error
        return render_template('authorize.html', user=user, grant=grant)
    if not user and 'username' in request.form:
        username = request.form.get('username')
        user = User.query.filter_by(username=username).first()
    if request.form['confirm']:
        grant_user = user
    else:
        grant_user = None
    return authorization.create_authorization_response(grant_user=grant_user)


@bp.route('/oauth/token', methods=['POST'])
def issue_token():
    return authorization.create_token_response()


@bp.route('/oauth/revoke', methods=['POST'])
def revoke_token():
    return authorization.create_endpoint_response('revocation')


@bp.route('/api/me')
@require_oauth('profile')
def api_me():
    user = current_token.user
    return jsonify(id=user.id, stripe=user.stripe_customer_id, username=user.username)

@bp.route('/intents/add_card')
@require_oauth('profile')
def intent_create_card():
    user = current_token.user

    if user.stripe_customer_id:
        customer = stripe.Customer.retrieve(user.stripe_customer_id)

    if not customer or 'deleted' in customer:
        customer = stripe.Customer.create()
        user.stripe_customer_id = customer.id
        db.session.commit()

    intent = stripe.SetupIntent.create(
        customer=customer['id'],
        usage='on_session'
    )

    return render_template('card_wallet.html', client_secret=intent.client_secret)

@bp.route('/intents/do_charge')
@require_oauth('profile', optional=True)
def intent_do_charge():
    if current_token:
        user = current_token.user
        customer_id = user.stripe_customer_id
        customer = stripe.Customer.retrieve(user.stripe_customer_id)

    args = request.args

    if customer and 'deleted' not in customer:
        payment_method = stripe.PaymentMethod.create(
          customer=customer_id,
          payment_method=args.get('payment_method'),
          stripe_account=args.get('stripe_account'),
        )

    fee = math.ceil(int(args.get('amount')) * 0.3)
    if fee < 50:
        fee = 50

    payment_intent = stripe.PaymentIntent.create(
        amount=args.get('amount'),
        currency='USD',
        payment_method=payment_method,
        payment_method_types=['card'],
        application_fee_amount=fee,
        stripe_account=args.get('stripe_account'),
    )

    return render_template('checkout.html', client_secret=payment_intent.client_secret, developer_account=args.get('stripe_account'))

@bp.route('/api/v1/delete_card/<card_id>', methods=['post'])
@require_oauth('profile')
def api_delete_card(card_id):
    user = current_token.user
    if user.stripe_customer_id:
        customer = stripe.Customer.retrieve(user.stripe_customer_id)

    payment_method = stripe.PaymentMethod.retrieve (card_id)
    if payment_method and customer and payment_method['customer'] == customer['id']:
        stripe.PaymentMethod.detach (card_id)

    return ''

@bp.route('/api/v1/cards')
@require_oauth('profile')
def api_get_cards():
    user = current_token.user

    if user.stripe_customer_id:
        cards = stripe.PaymentMethod.list(customer=user.stripe_customer_id, type="card")

    if cards:
        return jsonify(sources=cards['data'])

    return jsonify([])

@bp.route('/api/v1/success/<code>')
def api_success(code):
    return render_template('success.html', success_code=code)
