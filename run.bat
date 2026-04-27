@echo off
echo Установка зависимостей (если их еще нет)...
python -m pip install -r requirements.txt
echo.
echo Запуск бота...
python main.py
pause
