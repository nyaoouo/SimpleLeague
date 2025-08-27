import datetime
import logging
import time
import typing

from bottle import Bottle, request
from nyutils.password import make_password, validate_password

from .middleware import param_schema, load_user
from .utils import g_events, UserError, page_view_req_schema, page_view_res
from .models import WebUser, WebSession, WebPermission, SysCfg

api = Bottle()
logger = logging.getLogger(__name__)
_public_cfg = None


def get_public_cfg(force_update: bool = False):
    global _public_cfg
    if _public_cfg is None or force_update:
        _public_cfg = {cfg.key: cfg.data for cfg in SysCfg.select().where(SysCfg.public)}
    return _public_cfg


@g_events.set('server/cfg_change')
def on_cfg_change(*_):
    get_public_cfg(force_update=True)


def new_password_check(password: str):
    # TODO: length, complexity, common password check...
    if not password:
        raise UserError('Password cannot be empty')
    ...


@api.get('/public_cfg')
def public_cfg():
    return get_public_cfg()


@api.post('/register')
@param_schema({'username': str, 'password': str, 'data': dict})
def register():
    username = request.data['username']
    password = request.data['password']
    data = request.data.get('data', {})
    if WebUser.select().where(WebUser.username == username).exists():
        raise UserError("Username already exists")
    new_password_check(password)
    user = WebUser(username=username)
    user.password = make_password(password)
    user.data = data
    user.permissions = [WebPermission.USER]  # TODO: apply after email verification
    user.save()
    logger.info(f'New user registered: {username} from {request.environ.get("REMOTE_ADDR", "unknown")}')
    return user.to_client()


@api.post('/login')
@param_schema({'username': str, 'password': str})
def login():
    remote = request.environ.get('REMOTE_ADDR', 'unknown')
    if not (user := WebUser.try_login(request.data.get('username'), request.data.get('password'))):
        logger.warning(f'Failed login attempt for user {request.data.get("username")} from {remote}')
        raise UserError("Invalid username or password")
    session = WebSession.create_session(user, unique_type=10001)
    logger.info(f'User {user.username} logged in from {remote}')
    request.cookies['session'] = token = session.token
    return token


@api.post('/logout')
@load_user()
def logout():
    if request.session:
        request.session.destroy()


@api.get('ping')
def ping():
    return {'timestamp': int(time.time())}


@api.get('current_user')
@load_user()
def current_user():
    return request.session.user.to_client()


@api.post('/change_password')
@load_user()
@param_schema({'old_password': str, 'new_password': str})
def change_password():
    old_pw, new_pw = request.data['old_password'], request.data['new_password']
    user = request.session.user
    if not validate_password(old_pw, user.password):
        logger.warning(f'User {user.username} provided invalid old password for password change')
        raise UserError("Invalid old password")
    new_password_check(new_pw)
    user.password = make_password(new_pw)
    user.save()
    logger.info(f'User {user.username} changed password successfully')


@api.post('admin/list_users')
@load_user(required_permission=WebPermission.ADMIN)
@param_schema(page_view_req_schema())
def list_users():
    selector = WebUser.select()
    if query := request.data['query'].get('value'):
        selector = selector.where(WebUser.username.contains(query) | WebUser.data.contains(query))
    result = page_view_res(selector, request.data)
    return result


@api.post('admin/set_user_permission')
@load_user(required_permission=WebPermission.ADMIN)
@param_schema({'username': str, 'permissions': list[int]})
def set_user_permission():
    if not (user := WebUser.get_or_none(WebUser.username == request.data['username'])):
        raise UserError("User not found")
    p = request.data['permissions']
    if (WebPermission.ADMIN in p) != (WebPermission.ADMIN in user.permissions):
        raise UserError("Cannot change admin permission directly")
    old_permissions = user.permissions
    user.permissions = p
    user.save()
    logger.info(f'Admin {request.session.user.display_name} changed permissions for user {user.display_name} from {old_permissions} to {p}')


@api.post('admin/set_allow_login')
@load_user(required_permission=WebPermission.ADMIN)
@param_schema({'username': str, 'allow_login': bool})
def set_allow_login():
    act_user = request.session.user
    if request.data['username'] == act_user:
        raise UserError("Cannot change your own login permission")
    if not (user := WebUser.get_or_none(WebUser.username == request.data['username'])):
        raise UserError("User not found")
    old_allow_login = user.allow_login
    user.allow_login = request.data['allow_login']
    user.save()
    logger.info(f'Admin {act_user.display_name} changed allow_login for user {user.display_name} from {old_allow_login} to {user.allow_login}')


@api.post('admin/change_user_password')
@load_user(required_permission=WebPermission.ADMIN)
@param_schema({'username': str, 'new_password': str})
def admin_change_user_password():
    if not (user := WebUser.get_or_none(WebUser.username == request.data['username'])):
        raise UserError("User not found")
    new_password = request.data['new_password']
    new_password_check(new_password)
    user.password = make_password(new_password)
    user.save()
    for session in WebSession.select().where(WebSession.user == user):
        session.destroy()
    logger.info(f"Admin {request.session.user.username} changed password for user {user.username}")


@api.get('admin/list_cfg')
@load_user(required_permission=WebPermission.ADMIN)
def admin_list_cfg():
    return {cfg.key: cfg.data for cfg in SysCfg.select()}


@api.post('admin/set_cfg')
@load_user(required_permission=WebPermission.ADMIN)
@param_schema({'key': str, 'value': typing.Any})
def admin_set_cfg():
    key = request.data['key']
    value = request.data['value']
    if not SysCfg.has_key(key):
        raise UserError(f"Configuration key '{key}' does not exist")
    old_value = SysCfg.get_value(key)
    if not isinstance(value, type(old_value)):
        raise UserError(f"Configuration value type mismatch for key '{key}'")
    SysCfg.set_value(key, value)
    logger.info(f"Admin {request.session.user.username} set cfg {key} from {old_value} to {value}")
