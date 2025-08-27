import pathlib
import typing

from nyutils.eventloop import EventLoop
from nyutils.listener import Listener

g_loop = EventLoop()
g_events = Listener()
STATIC_DIR = pathlib.Path.cwd() / "static"


def page_view_req_schema(query_type=typing.Optional[dict[str, typing.Any]]):
    return {
        'page': int,
        'page_size': int,
        'query': query_type
    }


def page_view_res(selector, args):
    return {
        'total': selector.count(),
        'data': [item.to_client() for item in selector.paginate(args['page'], args['page_size'])]
    }


class UserError(Exception):
    def __init__(self, message: str, key: str = None):
        super().__init__(message)
        self.message = message
        self.key = key


