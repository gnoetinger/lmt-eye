rem create venv
rem python -m vent lmt_eye_exe
rem activate venv
rem lmt_eye_exe\Scripts\activate
rem populate packages:
rem in lmt_eye root package: pip install -r requirements.txt

rem C:\Users\fabri\lmt_eye_exe\Scripts\activate
pyInstaller lmt_eye_mcp.py -F --add-data res:res
pause
