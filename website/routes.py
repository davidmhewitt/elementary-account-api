import time
import math
import jwt
from datetime import datetime, timedelta
from flask import Blueprint, request, session, render_template, redirect, jsonify
from werkzeug.security import gen_salt
from authlib.integrations.flask_oauth2 import current_token
from authlib.oauth2 import OAuth2Error
from .models import db, User, OAuth2Client, Purchase, Application
from .oauth2 import authorization, require_oauth
from .secrets import stripe, secrets

shortRepoTokenLifetime = timedelta(minutes=10)
longRepoTokenLifetime = timedelta(days=3650)

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
    return jsonify(username=user.username)

@bp.route('/intents/add_card')
@require_oauth('profile')
def intent_create_card():
    user = current_token.user

    customer = None
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
    user_id = None
    if current_token:
        user = current_token.user
        user_id = user.id
        customer_id = user.stripe_customer_id
        customer = stripe.Customer.retrieve(user.stripe_customer_id)
    else:
        customer = []

    args = request.args

    # Clone payment method from platform account customer to temporary payment method
    if customer and 'deleted' not in customer and args.get('payment_method'):
        payment_method = stripe.PaymentMethod.create(
          customer=customer_id,
          payment_method=args.get('payment_method'),
          stripe_account=args.get('stripe_account'),
        )
    else:
        payment_method = ""

    fee = math.ceil(int(args.get('amount')) * 0.3)
    if fee < 50:
        fee = 50

    app_id = args.get('app_id')
    anon_id = args.get('anon_id')

    stripe_metadata = {
        'app_id': app_id,
        'user_id': user_id,
        'anon_id': anon_id
    }

    if payment_method:
        payment_intent = stripe.PaymentIntent.create(
            amount=args.get('amount'),
            currency='USD',
            payment_method=payment_method,
            payment_method_types=['card'],
            application_fee_amount=fee,
            stripe_account=args.get('stripe_account'),
            metadata=stripe_metadata
        )
    else:
        payment_intent = stripe.PaymentIntent.create(
            amount=args.get('amount'),
            currency='USD',
            payment_method_types=['card'],
            application_fee_amount=fee,
            stripe_account=args.get('stripe_account'),
            metadata=stripe_metadata
        )

    if payment_method:
        return render_template('checkout.html',
            client_secret=payment_intent.client_secret,
            developer_account=args.get('stripe_account'),
            app_name="Torrential",
            amount=math.floor(int(args.get('amount'))/100),
            last_four=payment_method.card.last4
        )
    else:
        return render_template('checkout.html',
            client_secret=payment_intent.client_secret,
            developer_account=args.get('stripe_account'),
            app_name="Torrential",
            amount=math.floor(int(args.get('amount'))/100)
        )

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
    else:
        return jsonify(sources=[])

    if cards:
        return jsonify(sources=cards['data'])

    return jsonify(sources=[])

@bp.route('/api/v1/success/<code>')
def api_success(code):
    return render_template('success.html', success_code=code)

@bp.route('/webhooks/payment_succeeded', methods=['POST'])
def webhook_success():
  payload = request.get_data()
  sig_header = request.headers.get('STRIPE_SIGNATURE')
  event = None

  try:
    event = stripe.Webhook.construct_event(
      payload, sig_header, secrets['INTENT_SUCCEEDED_SIGNING_KEY']
    )
  except ValueError as e:
    return "Invalid payload", 400
  except stripe.error.SignatureVerificationError as e:
    return "Invalid signature", 400

  event_dict = event.to_dict()
  if event_dict['type'] == "payment_intent.succeeded":
    intent = event_dict['data']['object']
    user_id = intent['metadata']['user_id']
    app_id = intent['metadata']['app_id']
    anon_id = intent['metadata']['anon_id']

    if app_id and user_id:
        purchase = Purchase(
            app_id = app_id,
            user_id = user_id
        )

        purchase.save_to_db()
    elif app_id and anon_id:
        purchase = AnonymousPurchase(
            app_id = app_id,
            anon_id = anon_id
        )

        purchase.save_to_db()

  return "OK", 200

@bp.route('/api/v1/get_tokens', methods=['POST'])
@require_oauth('profile', optional=True)
def api_get_tokens():
    current_user = None
    if current_token:
        current_user = current_token.user

    logged_in = current_user is not None

    data = request.get_json()

    denied = []
    tokens = {}
    for app_id in data['ids']:
        denied.append(app_id)

    if logged_in:
        for app_id in denied:
            if Purchase.find_purchase(current_user.id, app_id):
                denied.remove(app_id)
                tokens[app_id] = jwt.encode({
                    'sub': 'users/%d' % current_user.id,
                    'prefixes': [app_id],
                    'exp': datetime.utcnow() + longRepoTokenLifetime,
                    'name': 'auth.py',
                }, secrets['REPO_SIGNING_KEY'], algorithm='HS256').decode('utf-8')

    return {
        'denied': denied,
        'tokens': tokens
    }

@bp.route('/api/v1/app/<app_id>')
def api_get_app(app_id):
    app = Application.find_by_id(app_id)
    if not app:
        return {}, 404
    else:
        return {
            "id": app.app_id,
            "name": app.name,
            "stripe_key": app.stripe_key,
            "recommended_amount": app.recommended_amount
        }

@bp.route('/api/v1/get_temp_token')
def api_get_temp_token():
    data = request.get_json()
    app_id = data['id']

    tokens = {}
    tokens[app_id] = jwt.encode({
        'sub': 'users/%d' % 0,
        'prefixes': [app_id],
        'exp': datetime.utcnow() + shortRepoTokenLifetime,
        'name': 'auth.py',
    }, secrets['REPO_SIGNING_KEY'], algorithm='HS256').decode('utf-8')

    return {
        'tokens': tokens
    }

