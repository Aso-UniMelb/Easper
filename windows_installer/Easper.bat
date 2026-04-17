@echo off
set "PATH=%CD%\ffmpeg\bin;%PATH%"
call venv\Scripts\python.exe src\main.py