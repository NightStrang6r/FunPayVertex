"""
Создание и восстановление резервных копий.
"""
from logging import getLogger
import os
import zipfile
import shutil

logger = getLogger("FPV.backup")


def zipdir(path, zip_obj):
    """
    Рекурсивно архивирует папку.

    :param path: путь до папки.
    :param zip_obj: объект zip архива.
    """
    for root, dirs, files in os.walk(path):
        if os.path.basename(root) == "__pycache__":
            continue
        for file in files:
            zip_obj.write(os.path.join(root, file),
                          os.path.relpath(os.path.join(root, file),
                                          os.path.join(path, '..')))


def create_backup() -> int:
    """
    Создает резервную копию с папками storage и configs.

    :return: 0, если бэкап создан успешно, иначе - 1.
    """
    try:
        with zipfile.ZipFile("backup.zip", "w") as zip:
            zipdir("storage", zip)
            zipdir("configs", zip)
            zipdir("plugins", zip)
        return 0
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return 1


def extract_backup_archive() -> bool:
    """
    Разархивирует скачанный backup.zip. в storage/cache/backup/

    :return: True, если разархивировано. False в случае ошибок.
    """
    try:
        if os.path.exists("storage/cache/backup/"):
            shutil.rmtree("storage/cache/backup/", ignore_errors=True)
        os.makedirs("storage/cache/backup")

        with zipfile.ZipFile("storage/cache/backup.zip", "r") as zip:
            zip.extractall("storage/cache/backup/")
        return True
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return False


def install_backup() -> bool:
    """
    Устанавливает бэкап.
    """
    try:
        backup_folder = "storage/cache/backup"
        if not os.path.exists(backup_folder):
            return False

        for i in os.listdir(backup_folder):
            source = os.path.join(backup_folder, i)

            if os.path.isfile(source):
                shutil.copy2(source, i)
            else:
                shutil.copytree(source, os.path.join(".", i), dirs_exist_ok=True)
        return True
    except:
        logger.debug("TRACEBACK", exc_info=True)
        return False
