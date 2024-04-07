import asyncio

from ycappuccino_core import init, start
import logging
import argparse
import  os
# ------------------------------------------------------------------------------


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description='argument for app application')
    parser.add_argument('--root_path', type=str, help='root path of application yml')

    parser.add_argument('--config_yml_path', default="conf{}application.yml".format(os.sep), type=str,
                        help='path of application yml')

    args = parser.parse_args()
    yml_path = args.config_yml_path
    root_path = args.root_path
    init(root_path + os.sep + yml_path)
    # Run the server
    start()

if __name__ == "__main__":
    # Setup logs
    main()


