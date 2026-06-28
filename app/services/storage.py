import os
import secrets
from flask import current_app
from werkzeug.utils import secure_filename


ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "gif", "doc", "docx", "xls", "xlsx", "csv", "txt"}


def save_file(file_obj, subfolder="", rename=True):
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        upload_dir = os.path.join(upload_dir, subfolder)
    os.makedirs(upload_dir, exist_ok=True)

    original_name = file_obj.filename
    if rename:
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin"
        filename = secrets.token_hex(16) + "." + ext
    else:
        filename = original_name

    filepath = os.path.join(upload_dir, filename)
    file_obj.save(filepath)
    return filename


def get_file_path(filename, subfolder=""):
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        upload_dir = os.path.join(upload_dir, subfolder)
    return os.path.join(upload_dir, filename)


def retrieve_file(filename, subfolder=""):
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        upload_dir = os.path.join(upload_dir, subfolder)
    filepath = os.path.join(upload_dir, filename)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "rb") as f:
        return f.read()


def delete_file(filename, subfolder=""):
    filepath = get_file_path(filename, subfolder)
    if os.path.exists(filepath):
        os.remove(filepath)
        return True
    return False


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[-1].lower() in ALLOWED_EXTENSIONS


def get_file_size(filename, subfolder=""):
    filepath = get_file_path(filename, subfolder)
    if os.path.exists(filepath):
        return os.path.getsize(filepath)
    return 0


def list_user_files(user_id, subfolder=""):
    upload_dir = current_app.config["UPLOAD_FOLDER"]
    if subfolder:
        upload_dir = os.path.join(upload_dir, subfolder)
    if not os.path.exists(upload_dir):
        return []
    return [f for f in os.listdir(upload_dir) if os.path.isfile(os.path.join(upload_dir, f))]
