# middlewares for bottle
import datetime
import functools
import logging
import typing

from bottle import request, response, HTTPError
from nyutils.simple_validate import create_validator, ValidationError
from .models import WebSession
from .utils import UserError

logger = logging.getLogger(__name__)
SESSION_DURATION = datetime.timedelta(days=3)


class JsonApiMiddleware:
    def apply(self, callback, route):
        def wrapper(*args, **kwargs):
            try:
                result = callback(*args, **kwargs)
            except UserError as e:
                response.status = 400
                return {'success': 0, 'error': "UserError", 'details': str(e)}
            except Exception as e:
                response.status = 500
                logger.error(
                    f"Unhandled exception in route {route.rule}: {e}", exc_info=True)
                return {'success': 0, 'error': "InternalServerError"}
            else:
                return {'success': 1, 'result': result}

        return wrapper


def param_schema(schema):
    validator = create_validator(schema)

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if request.method == 'POST':
                try:
                    data = request.json
                except HTTPError:
                    raise UserError("Invalid JSON format")
                if data is None:
                    raise UserError("Request body cannot be empty")
            elif request.method == 'GET':
                data = request.query
            else:
                raise Exception(f"Unsupported method {request.method} for validation")
            try:
                validator(data, '')
            except ValidationError as e:
                raise UserError(str(e))
            request.data = data
            return func(*args, **kwargs)

        return wrapper

    return decorator


def load_user(required_permission: typing.Iterable[int] | int | None = None, require_login: bool = True):
    if isinstance(required_permission, int):
        required_permission = required_permission,

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            request.session = session = None
            if _session := request.cookies.get('session'):
                try:
                    request.session = session = WebSession.get_session(_session)
                except Exception:
                    ...
            if require_login and session is None:
                raise UserError("No session configured")
            if required_permission is not None and not (session and any(p in session.user.permissions for p in required_permission)):
                raise UserError('Permission denied')
            return func(*args, **kwargs)

        return wrapper

    return decorator


def apply_middlewares(app):
    app.install(JsonApiMiddleware())
    return app
