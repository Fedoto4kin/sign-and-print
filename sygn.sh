#!/bin/bash

# Записываем абсолютный путь к директории, где находится bash скрипт
SCRIPT_DIR=$(cd $(dirname "$0") && pwd)

# Путь к вашему виртуальному окружению
VENV_PATH="$SCRIPT_DIR/venv"

# Активация виртуального окружения
source "$VENV_PATH/bin/activate"
# Запуск скрипта Python
python main.py

# Деактивация виртуального окружения
deactivate