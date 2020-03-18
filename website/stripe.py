import stripe

secrets = {}

def init_stripe(app):
    stripe.api_key = app.config['STRIPE_KEY']
    secrets['intent_succeeded_signing_key'] = app.config['STRIPE_INTENT_SUCCESS_SIGNING_SECRET']
