# app="all"

"""
Created on 8 dec. 2017

component that provide a activity logger

@author: apisu
"""
# cohorte
from ycappuccino.api.core import IActivityLogger, IConfiguration

import logging
from logging.handlers import RotatingFileHandler

import os


_logger = logging.getLogger(__name__)

PREFIX_PROPERTY = "activity.logger"
LOG_DIR = "log"


class ActivityLogger(IActivityLogger):

    def __init__(self, config: IConfiguration, name: str = "main") -> None:
        super().__init__()

        self._config: IConfiguration = config
        self._name: str = name  # name of the component

        w_data_path = os.getcwd() + "/data"
        w_file = os.path.join(w_data_path, LOG_DIR)
        w_file_name = self._config.get(
            self.get_prefix_config() + ".file", self.get_default_log_name()
        )
        self._file: str = os.path.join(w_file, w_file_name)

        self._format = self._config.get(
            self.get_prefix_config() + ".format",
            "%(asctime)s;%(levelname)s;%(threadName)s;%(filename)s;%(module)s;%(funcName)s;(%(lineno)d);%(message)s",
        )
        self._file_nb: int = self._config.get(self.get_prefix_config() + ".nb", 10)
        self._file_size: int = self._config.get(
            self.get_prefix_config() + ".size", 20 * 1024 * 1024
        )
        self._level: int = self._config.get(self.get_prefix_config() + ".level", "INFO")

        w_data_path = os.getcwd() + "/data"
        if not os.path.isdir(w_data_path):
            os.mkdir(w_data_path)

        w_log_dir = os.path.join(w_data_path, LOG_DIR)
        if not os.path.isdir(w_log_dir):
            os.mkdir(w_log_dir)

        w_handler = RotatingFileHandler(
            self._file, "a", self._file_size, self._file_nb, "utf8", 0
        )

        w_log_formatter = logging.Formatter(self._format)
        w_handler.setFormatter(w_log_formatter)
        w_handler.setLevel(self._level)

        self.addHandler(w_handler)

    def get_prefix_config(self):
        """get the prefix for activity log depending of the instance default activity.logger"""
        if self._name == "default":
            return PREFIX_PROPERTY
        else:
            return PREFIX_PROPERTY + "." + self._name

    def get_default_log_name(self):
        if self._name != "default":
            return "Log-Activity-{}.log".format(self._name)
        else:
            return "Log-Activity.log"

    async def start(self) -> None:
        self.info(f"{self._name} is valid")

    async def stop(self) -> None:
        self.info(f"{self._name} is invalid")

    def __str__(self):
        return "filename={}, nb_file={}, file_size={}, level={}".format(
            self._file, self._file_nb, self._file_size, self._level
        )
