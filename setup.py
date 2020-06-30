#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

from setuptools import setup

assert sys.version >= "2.7", "Requires Python v2.7 or above."

with open("terncy/version.py") as f:
    exec(f.read())

    classifiers = [
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.2",
        "Programming Language :: Python :: 3.3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ]

    setup(
        name="terncy",
        version=__version__,
        author="Ruixiong Wen",
        author_email="rx.wen218@gmail.com",
        url="https://github.com/rxwen/python-terncy/",
        description="A Python library for controlling Terncy devices.",
        long_description="A Python library for controlling Terncy devices.",
        long_description_content_type="text/markdown",
        license="MIT",
        classifiers=classifiers,
        packages=["terncy"],
        install_requires=["enum-compat", "future"],
        test_suite="terncy.tests",
        tests_require=[],
    )
