import stripe

secrets = {}

def init_stripe(app):
    stripe.api_key = app.config['STRIPE_KEY']
    secrets['INTENT_SUCCEEDED_SIGNING_KEY'] = app.config['STRIPE_INTENT_SUCCESS_SIGNING_SECRET']
    secrets['REPO_SIGNING_KEY'] = app.config['REPO_SIGNING_KEY']
