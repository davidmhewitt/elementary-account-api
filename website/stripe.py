import stripe

def init_stripe(app):
    stripe.api_key = app.config['STRIPE_KEY']