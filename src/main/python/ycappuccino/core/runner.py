#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
start a YCappuccino application::

    python -m ycappuccino.core.runner --root_path <application directory>
"""
import argparse
import logging
import os

from ycappuccino.core.framework import Framework


def main(argv=None):
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="start a YCappuccino application")
    parser.add_argument(
        "--root_path",
        default=".",
        help="root path of the application (default: current directory)",
    )
    parser.add_argument(
        "--config_yml_path",
        default=os.path.join("conf", "application.yml"),
        help="path of the application yml, relative to the root path",
    )
    args = parser.parse_args(argv)

    framework = Framework.get_framework()
    framework.init(os.path.join(args.root_path, args.config_yml_path))
    # Run the server
    framework.start()


if __name__ == "__main__":
    main()
