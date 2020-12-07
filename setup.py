#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys

from setuptools import setup

assert sys.version >= "3.6", "Requires Python v3.6 or above."

with open("terncy/version.py") as f:
    exec(f.read())

    classifiers = [
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
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
        description="A Python library for controlling Terncy home automation system.",
        long_description="A Python library for controlling [Terncy](https://www.terncy.com) home automation system.",
        long_description_content_type="text/markdown",
        license="MIT",
        classifiers=classifiers,
        packages=["terncy"],
        install_requires=["enum-compat", "future"],
        test_suite="terncy.tests",
        tests_require=[],
    )
