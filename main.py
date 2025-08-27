import argparse
import logging
import pathlib
import sys

from nyutils.logging import install
from nyutils.database import init_database

from simple_league import App

cwd = pathlib.Path(sys.executable if hasattr(sys, 'frozen') else __file__).parent.resolve()
data_dir = pathlib.Path(getattr(sys, '_MEIPASS', pathlib.Path(__file__).parent)).resolve()


def main():
    argp = argparse.ArgumentParser()
    argp.add_argument('--debug', action='store_true')
    args = argp.parse_args()

    install(logging.INFO if hasattr(sys, 'frozen') and not args.debug else logging.DEBUG)
    init_database('main.db', '111111')
    App().serve()
    


if __name__ == '__main__':
    main()
