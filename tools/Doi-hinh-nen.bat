@echo off
chcp 65001 >nul
rem Drag an image (JPG, PNG, WebP, BMP or GIF, static or animated) onto this file to make it the
rem wallpaper of the "ASCII · My Wallpaper" theme in Orca.
if "%~1"=="" (
  echo Keo tha mot file anh vao file nay de dat lam hinh nen cho theme "ASCII · My Wallpaper".
  pause
  exit /b 1
)
python -I "%~dp0set-wallpaper.py" "%~1"
pause
