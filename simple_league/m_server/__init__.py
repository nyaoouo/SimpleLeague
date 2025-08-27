import logging
import pathlib

from bottle import abort, Bottle, static_file, redirect
from nyutils.password import make_password, rand_password
from .api import api
from .models import WebUser, WebPermission
from .middleware import apply_middlewares
from .utils import STATIC_DIR

logger = logging.getLogger(__name__)


def ensure_web_admin():
    if WebUser.select().count() == 0:
        password = rand_password(8)
        WebUser.create(username='admin', password=make_password(password), permissions=[p for p in WebPermission if p != WebPermission.NULL])
        logger.info("Created default admin user with username 'admin'.")
        with open('admin.txt', 'w') as f:
            f.write(f'admin\n{password}\n')


class Server:
    def __init__(self):
        self.api = Bottle()
        self.app = Bottle()

        apply_middlewares(self.api)
        apply_middlewares(api)

        self.api.mount('/server', api)
        self.app.mount('/api', self.api)

    def serve(self, host='0.0.0.0', port=80, static_dir=None):
        ensure_web_admin()
        if static_dir:
            logger.debug('Serving static files at %s', static_dir)
            static_dir = pathlib.Path(static_dir)

            # Find the default file
            default_file = None
            for default in (
                    'index.html',
                    'index.htm',
            ):
                if (static_dir / default).exists():
                    logger.debug('Serving default static file: %s', default)
                    default_file = default
                    break
            else:
                logger.error('Could not find static files at %s', static_dir)

            @self.app.get('/static/<fpath:path>')
            def serve_static(fpath):
                return static_file(fpath, root=STATIC_DIR)

            @self.app.get('/<fpath:path>')
            def serve_static(fpath):
                file_path = static_dir / fpath
                # Check if the requested file exists
                if file_path.exists() and file_path.is_file():
                    return static_file(fpath, root=static_dir)
                # If file doesn't exist and we have a default file, redirect to it
                elif default_file:
                    return static_file(default_file, root=static_dir)
                else:
                    return abort(404, "File not found")

            # Add a root route that serves the default file
            if default_file:
                @self.app.get('/')
                def serve_root():
                    return static_file(default_file, root=static_dir)

        # WSGIServer((host, port), self.app, handler_class=WebSocketHandler, log=logger).serve_forever()
        self.app.run(host=host, port=port)
