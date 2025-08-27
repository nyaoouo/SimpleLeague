import os
import pickle
import json
import re
import sys
import threading
import typing
import peewee

# HAS_SQL_CHIPPER = (os.environ.get('NO_SQLCIPHER') is None) if getattr(sys, 'frozen', False) else False
HAS_SQL_CHIPPER = False

if HAS_SQL_CHIPPER:
    import playhouse.sqlcipher_ext

    use_database = playhouse.sqlcipher_ext.SqlCipherDatabase(None)
else:
    use_database = peewee.SqliteDatabase(None)


def init_database(db_name, passphrase=""):
    if HAS_SQL_CHIPPER and passphrase:
        use_database.init(db_name, passphrase=passphrase)
    else:
        use_database.init(db_name)
    use_database.create_tables(BaseModel._models_)

    # use_database.execute_sql('PRAGMA journal_mode=WAL;')

    def simple_regexp(pattern, string, flags=0):
        if not isinstance(string, str):
            return 0
        return 1 if re.search(pattern, string, flags) else 0

    connection = use_database.connection()
    # selector = TestDb.select().where(TestDb.value.regexp(pattern))
    connection.create_function("REGEXP", 2, simple_regexp)
    connection.create_function("REGEXP", 3, simple_regexp)
    # selector = TestDb.select().where(peewee.fn.regexp_(pattern, TestDb.value) == 1) # to handle json fields
    connection.create_function("REGEXP_", 2, simple_regexp)
    connection.create_function("REGEXP_", 3, simple_regexp)
    connection.create_function("IF", 3, lambda condition, true_value,
                               false_value: true_value if condition else false_value)
    connection.create_function("JSON_EXTRACT", 2, lambda json_str, path: json.loads(
        json_str).get(path, None) if json_str else None)


write_lock = threading.Lock()
USE_PICKLE_FIELD = False

PICKLE_NONE = pickle.dumps(None)


class JsonField(peewee.TextField):
    def db_value(self, value):
        if value is None:
            return 'null'
        return json.dumps(value)

    def python_value(self, value):
        if value == 'null':
            return None
        return json.loads(value)


class PickleField(peewee.BlobField):
    def db_value(self, value):
        if value is None:
            return PICKLE_NONE
        return pickle.dumps(value)

    def python_value(self, value):
        if value == PICKLE_NONE:
            return None
        return pickle.loads(value)


DataField = PickleField if USE_PICKLE_FIELD else JsonField


class BaseModel(peewee.Model):
    _models_ = []
    if typing.TYPE_CHECKING:
        id: peewee.PrimaryKeyField

    class Meta:
        database = use_database

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseModel._models_.append(cls)

    def delete_instance(self, recursive=True, delete_nullable=False):
        return super().delete_instance(recursive, delete_nullable)

    def to_client(self) -> dict:
        """
        Convert the model instance to a dictionary suitable for sending to the client.
        Override this method in subclasses to customize the serialization.
        """
        return {}
