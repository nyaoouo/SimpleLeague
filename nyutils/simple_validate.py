import typing
import types


class ValidationError(Exception):
    def __init__(self, path, message):
        self.path = path
        self.message = message

    def __str__(self):
        return f"{self.path}: {self.message}"


def validate_simple(s):
    def validate_(o, p):
        if not isinstance(o, s):
            raise ValidationError(p, f"must be a {s}")

    return validate_


def validate_is_null(o, p):
    if o is not None:
        raise ValidationError(p, f"must be None")


def create_validator(s) -> typing.Callable[[typing.Any, str], None]:
    if s is int:
        return validate_simple(int)
    elif s is float:
        return validate_simple(float)
    elif s is str:
        return validate_simple(str)
    elif s is bool:
        return validate_simple(bool)
    elif s is bytes:
        return validate_simple(bytes)
    elif s is None or s is type(None):
        return validate_is_null
    elif s is list:
        return validate_simple((list, tuple))
    elif s is tuple:
        return validate_simple((list, tuple))
    elif s is dict:
        return validate_simple(dict)
    elif s is typing.Any:
        return lambda o, p: None

    if isinstance(s, types.GenericAlias) or isinstance(s, typing._GenericAlias):
        if s.__origin__ is list:
            el_validator = create_validator(s.__args__[0])

            def validate_(o, p):
                if not isinstance(o, list):
                    raise ValidationError(p, f"must be a list")
                for i, el in enumerate(o):
                    el_validator(el, f"{p}[{i}]")

            return validate_
        elif s.__origin__ is dict:
            key_type, val_type = s.__args__
            key_validator = create_validator(key_type)
            val_validator = create_validator(val_type)

            def validate_(o, p):
                if not isinstance(o, dict):
                    raise ValidationError(p, f"must be a dict")
                for k, v in o.items():
                    key_validator(k, f"{p}[{k}].key")
                    val_validator(v, f"{p}[{k}].value")

            return validate_
        elif s.__origin__ is tuple:
            validators = [create_validator(t) for t in s.__args__]

            def validate_(o, p):
                if not isinstance(o, (list, tuple)):
                    raise ValidationError(p, f"must be a tuple")
                if len(o) != len(validators):
                    raise ValidationError(p, f"must have {len(validators)} elements")
                for i, v in enumerate(validators):
                    v(o[i], f"{p}[{i}]")

            return validate_
        elif s.__origin__ is typing.Union:
            validators = [create_validator(t) for t in s.__args__]

            def validate_(o, p):
                for v in validators:
                    try:
                        v(o, p)
                        return
                    except ValidationError as e:
                        continue
                raise ValidationError(p, f"must be one of {s.__args__}")

            if type(None) in s.__args__:
                validate_.__nullable__ = True

            return validate_
        else:
            raise TypeError(f"unsupported type {s}")
    if isinstance(s, dict):
        validators = [(k, create_validator(v)) for k, v in s.items()]

        def validate_(o, p):
            if not isinstance(o, dict):
                raise ValidationError(p, f"must be a dict")
            for k, v in validators:
                if k not in o:
                    if getattr(v, "__nullable__", False): continue
                    raise ValidationError(p, f"missing key {k}")
                v(o[k], f"{p}[{k}]")

        return validate_

    raise TypeError(f"unsupported type {s}")


def validate(o, s, p):
    return create_validator(s)(o, p)
