@echo off
rem App anterior (Streamlit). La nueva es la de Django: usa iniciar.bat de la carpeta principal.
cd /d "%~dp0"
"..\.venv\Scripts\python.exe" -m streamlit run app.py
