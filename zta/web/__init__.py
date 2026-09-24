"""Flask transport adapter and composition root for the local prototype."""
from dataclasses import asdict
from datetime import timedelta
from functools import wraps
import hmac
import os
from pathlib import Path
import secrets

import click
from flask import Flask, jsonify, render_template, request, session

from ..accounts import LocalAccounts
from ..adapters.tflite import TFLiteFrameClassifier
from ..domain import InvalidFrame, ModelUnavailable
from ..policy import EvidencePolicy
from ..service import VerificationService, SessionNotFound, CapacityExceeded


def create_app(config=None, *, classifier=None, accounts=None):
    app = Flask(__name__)
    root = Path(__file__).resolve().parents[2]
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('ZTA_SECRET_KEY') or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=512 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=os.environ.get('ZTA_SECURE_COOKIES') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        DATABASE=str(root / 'instance' / 'accounts.db'),
        MODEL_PATH=str(root / 'models' / 'lighter_quant_model.tflite'),
        WINDOW_SIZE=75, FAKE_THRESHOLD=0.70,
    )
    if config:
        app.config.update(config)
    accounts = accounts or LocalAccounts(app.config['DATABASE'])
    service = VerificationService(
        classifier if classifier is not None else TFLiteFrameClassifier(app.config['MODEL_PATH']),
        EvidencePolicy(app.config['WINDOW_SIZE'], app.config['FAKE_THRESHOLD']),
    )
    app.extensions['verification'] = service
    app.extensions['accounts'] = accounts

    @app.before_request
    def csrf_protection():
        if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
            expected = session.get('csrf')
            supplied = request.headers.get('X-CSRF-Token', '')
            if not expected or not hmac.compare_digest(expected, supplied):
                return jsonify(error='Invalid CSRF token'), 403

    @app.after_request
    def response_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        response.headers['Permissions-Policy'] = 'camera=(self), microphone=()'
        return response

    def authenticated(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('username'):
                return jsonify(error='Sign in first'), 401
            return fn(*args, **kwargs)
        return wrapped

    @app.get('/')
    def index():
        session.setdefault('csrf', secrets.token_hex(32))
        return render_template('index.html', csrf=session['csrf'], username=session.get('username'))

    @app.post('/api/login')
    def login():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not accounts.authenticate(data.get('username'), data.get('password')):
            return jsonify(error='Invalid username or password'), 401
        session.clear()
        session.permanent = True
        session['username'] = data['username']
        session['csrf'] = secrets.token_hex(32)
        # Each login has a distinct capture owner, including logins by the same user.
        session['capture_owner'] = secrets.token_hex(32)
        return jsonify(username=data['username'])

    @app.post('/api/logout')
    @authenticated
    def logout():
        key = session.get('capture_id')
        if key:
            try:
                service.stop(key, session['capture_owner'])
            except SessionNotFound:
                pass
        session.clear()
        return '', 204

    @app.post('/api/captures')
    @authenticated
    def start():
        data = request.get_json(silent=True)
        if data is None and not request.get_data():
            data = {}
        if not isinstance(data, dict):
            return jsonify(error='Expected a JSON object'), 400
        if 'model' in data:
            return jsonify(error='Model selection is not supported; this service uses CNN'), 400
        previous = session.get('capture_id')
        if previous:
            try:
                service.stop(previous, session['capture_owner'])
            except SessionNotFound:
                pass
        key = service.start(session['capture_owner'])
        session['capture_id'] = key
        return jsonify(capture_id=key), 201

    @app.post('/api/captures/<key>/frames')
    @authenticated
    def frame(key):
        if request.mimetype != 'image/jpeg':
            return jsonify(error='Expected image/jpeg'), 415
        encoded = request.get_data()
        if not encoded:
            return jsonify(error='Empty frame'), 400
        evidence = service.submit(key, session['capture_owner'], encoded)
        return jsonify(asdict(evidence))

    @app.delete('/api/captures/<key>')
    @authenticated
    def stop(key):
        service.stop(key, session['capture_owner'])
        if session.get('capture_id') == key:
            session.pop('capture_id')
        return '', 204

    @app.errorhandler(InvalidFrame)
    def invalid_frame(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(ModelUnavailable)
    def unavailable(exc):
        app.logger.exception('Model unavailable')
        return jsonify(error='Video model unavailable; no evidence recorded'), 503

    @app.errorhandler(SessionNotFound)
    def missing(exc):
        return jsonify(error=str(exc)), 404

    @app.errorhandler(CapacityExceeded)
    def capacity(exc):
        return jsonify(error=str(exc)), 429

    @app.errorhandler(413)
    def oversized(exc):
        return jsonify(error='Frame exceeds 512 KiB'), 413

    @app.cli.command('create-user')
    @click.argument('username')
    @click.password_option(confirmation_prompt=True)
    def create_user(username, password):
        """Provision a local account without public self-registration."""
        try:
            accounts.create(username, password)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f'Created account: {username}')

    return app
