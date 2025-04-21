from flask import Flask
from flask_cors import CORS
from flask_migrate import Migrate
from .models import db, setup_relationships
from .api.auth import auth_bp
from .api.store import store_bp
from .api.product import product_bp
from .api.prompt import prompt_bp
from .api.seo import seo_bp
from .api.analytics import analytics_bp
import os
from celery import Celery

def create_app(test_config=None):
    app = Flask(__name__)
    CORS(app)
    
    # Configure the Flask application
    if test_config is None:
        app.config.from_mapping(
            SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
            SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///shopify_app.db'),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            AUTH_TOKEN_EXPIRES=86400,  # 24 hours in seconds
            SHOPIFY_API_KEY=os.environ.get('SHOPIFY_API_KEY'),
            SHOPIFY_API_SECRET=os.environ.get('SHOPIFY_API_SECRET')
        )
    else:
        app.config.update(test_config)

    # Initialize extensions
    db.init_app(app)
    migrate = Migrate(app, db)

    # Set up model relationships
    with app.app_context():
        setup_relationships()
        db.create_all()

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(store_bp, url_prefix='/api')
    app.register_blueprint(product_bp, url_prefix='/api')
    app.register_blueprint(prompt_bp, url_prefix='/api')
    app.register_blueprint(seo_bp, url_prefix='/api')
    app.register_blueprint(analytics_bp, url_prefix='/api')

    celery = Celery('shopifyapp',
                    broker='redis://localhost:6379/0',
                    backend='redis://localhost:6379/0')

    celery.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
    )

    return app 