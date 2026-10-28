"""Flask transport adapter and composition root for the local prototype."""
from datetime import timedelta
from functools import wraps
import hmac
import json
import os
from pathlib import Path
import secrets

import click
from flask import Flask, Response, jsonify, render_template, request, session, stream_with_context

from ..accounts import LocalAccounts
from ..adapters.litert import LiteRTFrameClassifier
from ..camera import CameraBusy, CameraRunNotFound, RGBDCameraPipeline, TERMINAL_PHASES
from ..policy import EvidencePolicy
from ..service import VerificationService, SessionNotFound, CapacityExceeded


def create_app(config=None, *, classifier=None, accounts=None, capture_pipeline=None):
    app = Flask(__name__)
    root = Path(__file__).resolve().parents[2]
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('ZTA_SECRET_KEY') or secrets.token_hex(32),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Strict',
        SESSION_COOKIE_SECURE=os.environ.get('ZTA_SECURE_COOKIES') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        DATABASE=str(root / 'instance' / 'accounts.db'),
        MODEL_PATH=str(root / 'models' / 'lighter_quant_model.tflite'),
        WINDOW_SIZE=75, FAKE_THRESHOLD=0.70,
        REALSENSE_SERIAL=os.environ.get('ZTA_REALSENSE_SERIAL'),
        SAMPLE_INTERVAL=0.2, CAMERA_PREVIEW=True,
    )
    if config:
        app.config.update(config)
    accounts = accounts or LocalAccounts(app.config['DATABASE'])
    service = VerificationService(
        classifier if classifier is not None else LiteRTFrameClassifier(app.config['MODEL_PATH']),
        EvidencePolicy(app.config['WINDOW_SIZE'], app.config['FAKE_THRESHOLD']),
    )
    capture_pipeline = capture_pipeline or RGBDCameraPipeline(
        service.submit,
        device_serial=app.config['REALSENSE_SERIAL'],
        sample_interval=app.config['SAMPLE_INTERVAL'],
        preview=app.config['CAMERA_PREVIEW'],
    )
    app.extensions['verification'] = service
    app.extensions['accounts'] = accounts
    app.extensions['capture_pipeline'] = capture_pipeline

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
        response.headers['Permissions-Policy'] = 'camera=(), microphone=()'
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
                capture_pipeline.stop(key, session['capture_owner'])
            except CameraRunNotFound:
                pass
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
                capture_pipeline.stop(previous, session['capture_owner'])
            except CameraRunNotFound:
                pass
            try:
                service.stop(previous, session['capture_owner'])
            except SessionNotFound:
                pass
        key = service.start(session['capture_owner'])
        try:
            capture_pipeline.start(key, session['capture_owner'])
        except Exception:
            service.stop(key, session['capture_owner'])
            raise
        session['capture_id'] = key
        return jsonify(capture_id=key), 201

    @app.get('/api/captures/<key>/events')
    @authenticated
    def capture_events(key):
        owner = session['capture_owner']

        @stream_with_context
        def generate():
            version = -1
            while True:
                previous = version
                try:
                    version, state = capture_pipeline.wait_for_update(key, owner, version)
                except CameraRunNotFound:
                    return
                if version == previous:
                    yield ': keep-alive\n\n'
                    continue
                yield f"data: {json.dumps(state)}\n\n"
                if state['phase'] in TERMINAL_PHASES:
                    return

        return Response(generate(), mimetype='text/event-stream')

    @app.delete('/api/captures/<key>')
    @authenticated
    def stop(key):
        owner = session['capture_owner']
        try:
            capture_pipeline.stop(key, owner)
        except CameraRunNotFound:
            pass
        service.stop(key, owner)
        if session.get('capture_id') == key:
            session.pop('capture_id')
        return '', 204

    @app.errorhandler(SessionNotFound)
    def missing(exc):
        return jsonify(error=str(exc)), 404

    @app.errorhandler(CameraRunNotFound)
    def missing_camera_run(exc):
        return jsonify(error=str(exc)), 404

    @app.errorhandler(CameraBusy)
    def busy_camera(exc):
        return jsonify(error=str(exc)), 409

    @app.errorhandler(CapacityExceeded)
    def capacity(exc):
        return jsonify(error=str(exc)), 429

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
