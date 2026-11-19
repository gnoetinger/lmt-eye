rem create venv
rem python -m vent lmt_eye_exe
rem activate venv
rem lmt_eye_exe\Scripts\activate
rem populate packages:
rem in lmt_eye root package: pip install -r requirements.txt

rem C:\Users\fabri\lmt_eye_exe\Scripts\activate
rem test: pyInstaller lmt_eye_mcp.py -F --add-data res:res
pyinstaller --onefile --icon=res/lmt_eye_icon.png --add-data "res/lmt_eye_icon.png;res" --add-data "res/template;res/template" --add-data "res/assets;res/assets" --add-data "res/mouse_run.gif;res" --add-data "events/custom;events/custom" lmt_eye_mcp.py

pause
