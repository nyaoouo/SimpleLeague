import json

import atexit
import datetime
import enum
import logging
import uuid

from nyutils.database import *
from nyutils.password import validate_password
from .utils import g_events, g_loop

tbl_prefix = 'server_'
logger = logging.getLogger(__name__)


class SysCfg(BaseModel):
    class Meta:
        table_name = tbl_prefix + 'sys_cfg'

    key = peewee.CharField(unique=True)
    # public config can be read by all web users
    public = peewee.BooleanField(default=False)
    data = DataField()

    @classmethod
    def has_key(cls, k: str):
        return cls.select().where(cls.key == k).exists()

    @classmethod
    def get_value(cls, k: str, default=None, create=False):
        if res := cls.get_or_none(key=k):
            return res.data
        elif create:
            res = cls(key=k)
            res.data = default
            res.save()
        return default

    @classmethod
    def set_value(cls, k: str, value, public: bool = None):
        if (res := cls.get_or_none(key=k)) is None:
            res = cls(key=k)
        if res.data != value:
            res.data = value
            if public is not None:
                res.public = public
            res.save()
            g_events.invoke('server/cfg_change', k, value)
        return res


class WebPermission(enum.IntEnum):
    NULL = 0
    USER = 1
    MANAGER = 2
    ADMIN = 3


class WebUser(BaseModel):
    class Meta:
        table_name = tbl_prefix + 'web_user'

    username = peewee.CharField(unique=True)
    password = peewee.CharField(default='')
    last_login = peewee.DateTimeField(null=True)
    allow_login = peewee.BooleanField(default=True)
    permissions = JsonField(default=[])

    data = JsonField(default={}) # user custom data, e.g. nickname, avatar, email, etc. (not sensitive info)

    @property
    def display_name(self):
        return self.data.get('nickname', self.username)

    @classmethod
    def try_login(cls, username: str, password: str) -> 'WebUser | None':
        user = cls.get_or_none(cls.username == username)
        if not user:
            return None  # user not found
        if not user.allow_login:
            return None  # user not allowed to login
        if not user.password:
            return user  # no password set
        if not isinstance(password, str):
            return None
        try:
            if not validate_password(password, user.password):
                return None
        except ValueError:
            logger.error(
                f"server error: invalid password hash format for user {username}: {user.password!r}", exc_info=True)
            return None
        user.last_login = datetime.datetime.now()
        user.save()
        return user

    def to_client(self):
        return {
            "username": self.username,
            "permissions": self.permissions,
            "last_login": self.last_login.timestamp() if self.last_login else 0,
            "allow_login": self.allow_login,
        }


class WebSession(BaseModel):
    class Meta:
        table_name = tbl_prefix + 'web_session'

    user = peewee.ForeignKeyField(
        WebUser, backref='sessions', on_delete='CASCADE')
    token = peewee.CharField(unique=True)
    unique_type = peewee.IntegerField()
    created_at = peewee.DateTimeField()
    valid_until = peewee.DateTimeField(null=True)
    data = DataField(default={})

    @classmethod
    def create_session(cls, user: WebUser, unique_type: int = 0, valid_duration: datetime.timedelta | None = datetime.timedelta(days=30), data=None) -> 'WebSession':
        if unique_type:
            for session in WebSession.select().where(WebSession.user == user, WebSession.unique_type == unique_type):
                session.destroy()

        now = datetime.datetime.now()
        valid_until = None if valid_duration is None else (
                now + valid_duration)
        t_pre = now.strftime('%Y%m%d-%H%M%S-')
        while True:
            try:
                return WebSession.create(user=user, token=t_pre + str(uuid.uuid4()), unique_type=unique_type, created_at=now, valid_until=valid_until, data=data or {})
            except peewee.IntegrityError:
                # If the token already exists, generate a new one
                ...

    @classmethod
    def get_session(cls, token: str) -> 'WebSession | None':
        session = WebSession.get_or_none(WebSession.token == token)
        if not session:
            raise KeyError
        if session.valid_until and session.valid_until < datetime.datetime.now():
            session.destroy()
            raise ValueError
        return session

    @classmethod
    def destroy_session(cls, token: str):
        if session := cls.get_or_none(cls.token == token):
            session.destroy()

    def update_expiration(self, valid_duration: datetime.timedelta | None = datetime.timedelta(days=30)):
        if not valid_duration:
            return
        self.valid_until = datetime.datetime.now() + valid_duration
        self.save()

    def destroy(self):
        token = self.token
        self.delete_instance()
        g_events.invoke('server/session_drop', token)
