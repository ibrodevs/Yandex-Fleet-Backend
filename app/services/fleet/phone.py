from __future__ import annotations


def normalize_phone(phone: str | None, *, default_country_code: str = "996") -> str | None:
    """Normalize a phone to a comparable international representation.

    Numbers that already contain an international prefix are preserved. A local
    number beginning with zero uses the configurable default country code.
    """

    if not phone:
        return None
    raw = str(phone).strip()
    had_plus = raw.startswith("+")
    digits = "".join(character for character in raw if character.isdigit())
    if not digits:
        return None

    country_code = "".join(character for character in default_country_code if character.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    elif had_plus:
        pass
    elif digits.startswith("0") and country_code:
        digits = country_code + digits[1:]
    elif country_code and len(digits) <= 9:
        digits = country_code + digits

    if len(digits) < 7 or len(digits) > 15:
        return None
    return f"+{digits}"
