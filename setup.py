"""Setup file for qsolverlib."""

import setuptools

setuptools.setup(
    name="ycappuccino_core",
    version="0.0.1",
    description="A framewore ycappuccino_core library for declaring component based software app",
    url="https://github.com/Y-Blues/core",
    author="Aurelien Pisu",
    author_email="aurelie.pisu@gmail.com",
    license=None,
    classifiers=[
        "Programming Language :: Python"
    ],
    install_requires=[
        'ipopo',
    ],
    packages=setuptools.find_packages(),
    python_requires=">=3.9"
)