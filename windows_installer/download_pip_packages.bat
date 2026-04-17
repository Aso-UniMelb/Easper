@echo off
pip download -d ./pip_packages setuptools wheel pip
pip install --no-index --find-links=./pip_packages setuptools wheel pip
