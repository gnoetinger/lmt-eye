# LMT-EYE

A PyQt6-based desktop application for behavioral analysis and event detection in animal research. LMT-EYE provides tools for analyzing, comparing, and visualizing behavioral data and events from an .sqlite database created by LMT.

Find an example of what LMT-EYE can do here :
[LMT-EYE example](https://micecraft.org/eye-example)

<div align="center">
  <img src="res/lmt_eye_icon.png" alt="LMT-EYE Icon" width="300">
</div>


## Requirements

Find the complete list of dependencies here: [requirements.txt](requirements.txt). To install all dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Either use the .exe file or run `lmt-eye.py` script. To create the .exe file (a standalone executable) using PyInstaller run the following command at root project:

```bash
pyinstaller -p LMT --onefile --icon=res/lmt_eye_icon.png --add-data "res/lmt_eye_icon.png;res" --add-data "res/template;res/template" --add-data "res/assets;res/assets" --add-data "res/mouse_run.gif;res" lmt_eye.py
```
(This command can be found in `lmt-eye.py` script)

## Custom Events

Please feel free to submit a Pull Request to add your own custom events for everyone.

## Project Structure

```
lmt-eye/
├── lmt_eye.py                 # Main application
├── requirements.txt           # Python dependencies
├── lmtanalysis/               # Scripts from lmt-analysis 
│   ├── Animal.py              # Animal and AnimalPool class
│   └── ...
├── events/                    # Behavioral events builder
│   ├── official/              # Official events (from lmt-analysis)
│   │   ├── BuildEventFlickering.py
│   │   └── ...
│   └── custom/                # Custom events
│       └── ...
├── scripts/                   # Data processing and analysis scripts used by LMT-EYE
│   └── ...
├── reports/                   # Report generation scripts
│   ├── ...
├── widgets/                   # LMT-EYE windows (PyQt6 widgets)
│   └── ...
└── res/                       # Resources
    ├── assets/                # Image assets
    └── template/              # Report templates
```

## Acknowledgments

This app is created based on the work of Fabrice De Chaumont and others.

Find the original repository here: [lmt-analysis](https://github.com/fdechaumont/lmt-analysis)
