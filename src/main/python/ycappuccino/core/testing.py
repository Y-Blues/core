"""
Helpers for tests of YCappuccino applications: throwaway applications written
in temporary directories, and polling.
"""

import os
import shutil
import sys
import tempfile
import textwrap
import time
import uuid


def wait_until(predicate, timeout=5.0):
    """poll the predicate until it returns a truthy value or the timeout expires"""
    deadline = time.monotonic() + timeout
    while True:
        result = predicate()
        if result or time.monotonic() > deadline:
            return result
        time.sleep(0.01)


def read_file(path):
    if not os.path.exists(path):
        return ""
    with open(path) as file:
        return file.read()


class TemporaryApplication(object):
    """
    Writes an application in a temporary directory, used as current directory while open.
    Every occurrence of PACKAGE in file names and contents is replaced by a unique package name.
    """

    def __init__(self, files):
        self.package = "ycctest_" + uuid.uuid4().hex[:8]
        self.root = os.path.realpath(tempfile.mkdtemp(prefix="ycappuccino-"))
        self._previous_cwd = None
        for relative_path, content in files.items():
            path = os.path.join(self.root, relative_path.replace("PACKAGE", self.package))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as file:
                file.write(textwrap.dedent(content).replace("PACKAGE", self.package))

    @property
    def yml_path(self):
        return os.path.join(self.root, "conf", "application.yml")

    def module(self, name):
        return sys.modules[self.package + "." + name]

    def open(self):
        self._previous_cwd = os.getcwd()
        os.chdir(self.root)
        return self

    def close(self):
        if self._previous_cwd is not None:
            os.chdir(self._previous_cwd)
            self._previous_cwd = None
        while self.root in sys.path:
            sys.path.remove(self.root)
        for name in list(sys.modules):
            if name == self.package or name.startswith(self.package + "."):
                del sys.modules[name]
        shutil.rmtree(self.root, ignore_errors=True)
