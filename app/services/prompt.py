from __future__ import annotations

from app.core.config import Settings
from app.core.errors import AppError, BadRequestError, PayloadTooLargeError


def load_system_prompt(settings: Settings) -> str:
    path = settings.system_prompt_path
    if not path.exists():
        raise AppError(f"{path.name} was not found")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise AppError(f"{path.name} is empty")
    return text


def load_dataset(settings: Settings, upload: bytes | None) -> str:
    if upload is None:
        path = settings.dataset_path
        if not path.exists():
            raise BadRequestError(f"{path.name} was not found")
        text = path.read_text(encoding="utf-8-sig")
    else:
        if len(upload) > settings.max_upload_bytes:
            raise PayloadTooLargeError(f"CSV upload exceeds {settings.max_upload_bytes} bytes")
        try:
            text = upload.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise BadRequestError("CSV file must be UTF-8") from exc

    if not text.strip():
        raise BadRequestError("Dataset is empty")
    return text


def opening_input(system_prompt: str, csv_text: str) -> str:
    return (
        "System prompt:\n"
        f"{system_prompt}\n\n"
        "Dataset.csv follows. Remember these examples. "
        "Confirm briefly that you received the system prompt and the dataset. "
        "Later messages are the shop messages to price.\n\n"
        f"{csv_text}"
    )
