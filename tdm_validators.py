from pathlib import Path


MAX_SIGNATURE_SIZE_BYTES = 2 * 1024 * 1024


def is_valid_phone(phone: str) -> bool:
    return phone.isdigit() and len(phone) == 11


def is_valid_direct_auc(text: str) -> bool:
    try:
        return float(text.strip()) > 0
    except (ValueError, AttributeError):
        return False


def validate_signature_file(file_path: str) -> str | None:
    try:
        file_size = Path(file_path).stat().st_size
    except OSError:
        return "Unable to read the selected signature file."
    if file_size > MAX_SIGNATURE_SIZE_BYTES:
        return "Signature image must be 2 MB or smaller."
    return None
