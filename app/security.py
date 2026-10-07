import hmac
import re


def secret_matches(received: str | None, expected: str) -> bool:
    if not received:
        return False
    return hmac.compare_digest(received.encode(), expected.encode())


def normalize_phone(raw: str) -> str:
    return re.sub(r"\D", "", raw)


def phone_variants(phone: str) -> set[str]:
    """Formas equivalentes de um número brasileiro, com e sem o nono dígito.

    WhatsApp às vezes identifica números antigos sem o 9 depois do DDD.
    """
    digits = normalize_phone(phone)
    variants = {digits}
    if digits.startswith("55"):
        ddd, local = digits[2:4], digits[4:]
        if len(local) == 9 and local.startswith("9"):
            variants.add(f"55{ddd}{local[1:]}")
        elif len(local) == 8:
            variants.add(f"55{ddd}9{local}")
    return variants


def is_owner(phone: str, owner_phone: str) -> bool:
    return normalize_phone(phone) in phone_variants(owner_phone)
