@echo off
set PY_VER=3.11
py -%PY_VER% -m venv venv
call venv\Scripts\activate.bat
pip install --no-index --find-links=./pip_packages setuptools wheel pip
pip install --no-index --find-links=./pip_packages --no-build-isolation -r requirements.txt
echo Environment setup complete!
