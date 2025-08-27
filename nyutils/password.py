import base64
import hashlib
import os
import random
import string

password_pool = [c for c in string.ascii_letters + string.digits if c not in 'lI1oO0']  # + list('_-,.!@#$%^&')
rand_password = lambda n: ''.join(random.choices(password_pool, k=n))


def validate_password(password: str, password_hash: str):
    if not password and not password_hash: return True
    try:
        alg, enc, data = password_hash.split('|', 2)
        match enc:
            case 'h':
                data_ = bytes.fromhex(data)
            case 'b':
                data_ = base64.b64decode(data)
            case 'u':
                data_ = data.encode('utf-8')
            case _:
                raise ValueError('invalid password hash encoding')
    except ValueError as e:
        raise ValueError('invalid password hash format') from e
    password_ = password.encode('utf-8')
    match alg:
        case 'none':
            return password_ == data_
        case 'md5':
            return hashlib.md5(password_ + data_[16:]).digest() == data_[:16]
        case 'sha1':
            return hashlib.sha1(password_ + data_[20:]).digest() == data_[:20]
        case 'sha256':
            return hashlib.sha256(password_ + data_[32:]).digest() == data_[:32]
        case 'sha512':
            return hashlib.sha512(password_ + data_[64:]).digest() == data_[:64]
        case _:
            return ValueError('invalid password hash algorithm')


def make_password(password: str, alg: str = 'sha256', encoding: str = 'b'):
    if not password: return ''
    password_ = password.encode('utf-8')
    match alg:
        case 'none':
            data = password_
        case 'md5':
            data = hashlib.md5(password_ + (s := os.urandom(0x10))).digest() + s
        case 'sha1':
            data = hashlib.sha1(password_ + (s := os.urandom(0x14))).digest() + s
        case 'sha256':
            data = hashlib.sha256(password_ + (s := os.urandom(0x20))).digest() + s
        case 'sha512':
            data = hashlib.sha512(password_ + (s := os.urandom(0x40))).digest() + s
        case _:
            raise ValueError('invalid password hash algorithm')
    match encoding:
        case 'h':
            return alg + '|h|' + data.hex()
        case 'b':
            return alg + '|b|' + base64.b64encode(data).decode("utf-8")
        case 'u':
            return alg + '|u|' + data.decode("utf-8")
        case _:
            raise ValueError('invalid password hash encoding')
