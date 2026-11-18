import copy
import os
import yaml

BASE_CONFIG_PATH = 'config.yml'
LOCAL_CONFIG_PATH = 'config.local.yml'

# Ключи, которые хранятся только локально (не в общем config.yml)
_LOCAL_IMAGE_KEYS = ('path', 'scale')


def _deep_merge(base, overlay):
    """Рекурсивно накладывает overlay на base (словари)."""
    result = copy.deepcopy(base)
    if not overlay:
        return result
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _load_yaml(path):
    if not os.path.isfile(path):
        return {}
    with open(path, 'r', encoding='utf-8') as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _extract_local_overlay(full_config):
    """Выделить персональные настройки для config.local.yml."""
    path_cfg = full_config.get('path') or {}
    images = full_config.get('images') or {}
    font = full_config.get('font') or {}

    local = {
        'path': {
            'default': path_cfg.get('default'),
            'last_open': path_cfg.get('last_open'),
            'last_save': path_cfg.get('last_save'),
        },
        'font': {
            'size': font.get('size'),
        },
        'images': {},
        'texts': copy.deepcopy(full_config.get('texts') or []),
    }

    for name in ('signature', 'print'):
        src = images.get(name) or {}
        local['images'][name] = {
            key: src[key] for key in _LOCAL_IMAGE_KEYS if key in src
        }

    return local


def load_config():
    base = _load_yaml(BASE_CONFIG_PATH)
    local = _load_yaml(LOCAL_CONFIG_PATH)
    return _deep_merge(base, local)


config = load_config()


def save_config():
    """Сохраняет персональные настройки в config.local.yml."""
    local_data = _extract_local_overlay(config)
    with open(LOCAL_CONFIG_PATH, 'w', encoding='utf-8') as fh:
        yaml.safe_dump(local_data, fh, allow_unicode=True, sort_keys=False)


def reload_config():
    """Перечитать base+local в глобальный config (на месте)."""
    fresh = load_config()
    config.clear()
    config.update(fresh)


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
