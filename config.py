import os
import yaml

CONFIG_PATH = 'config.yml'

with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    config = yaml.safe_load(config_file)


def save_config():
    with open(CONFIG_PATH, 'w', encoding='utf-8') as config_file:
        yaml.safe_dump(config, config_file, allow_unicode=True, sort_keys=False)


def _path_section():
    return config.setdefault('path', {})


def _usable_dir(path):
    if not path:
        return None
    expanded = os.path.expanduser(str(path))
    if os.path.isdir(expanded):
        return expanded
    return None


def get_initial_dir(kind='open'):
    """Директория для диалога: last_open / last_save, иначе default."""
    section = _path_section()
    if kind == 'save':
        for key in ('last_save', 'last_open', 'default'):
            remembered = _usable_dir(section.get(key))
            if remembered:
                return remembered
    else:
        for key in ('last_open', 'default'):
            remembered = _usable_dir(section.get(key))
            if remembered:
                return remembered
    return os.path.expanduser('~')


def remember_dir(file_or_dir, kind='open'):
    """Запомнить каталог последнего открытия или сохранения."""
    if not file_or_dir:
        return
    path = os.path.expanduser(str(file_or_dir))
    directory = path if os.path.isdir(path) else os.path.dirname(path)
    directory = _usable_dir(directory)
    if not directory:
        return
    section = _path_section()
    key = 'last_open' if kind == 'open' else 'last_save'
    if section.get(key) == directory:
        return
    section[key] = directory
    try:
        save_config()
    except OSError:
        pass
