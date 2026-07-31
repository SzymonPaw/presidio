"""Funkcje do walidacji polskich identyfikatorów za pomocą sum kontrolnych."""

def validate_nip(nip: str) -> bool:
    """Sprawdza poprawnosc NIP (NIP)."""
    nip = nip.replace("-", "").replace(" ", "")
    if len(nip) != 10 or not nip.isdigit():
        return False
    weights = [6, 5, 7, 2, 3, 4, 5, 6, 7]
    checksum = sum(int(nip[i]) * weights[i] for i in range(9))
    return (checksum % 11) == int(nip[9])


def validate_regon(regon: str) -> bool:
    """Sprawdza poprawnosc REGON (9 lub 14 cyfr)."""
    regon = regon.replace("-", "").replace(" ", "")
    if len(regon) not in (9, 14) or not regon.isdigit():
        return False
    weights_9 = [8, 9, 2, 3, 4, 5, 6, 7]
    checksum_9 = sum(int(regon[i]) * weights_9[i] for i in range(8))
    check_digit_9 = checksum_9 % 11
    if check_digit_9 == 10:
        check_digit_9 = 0
    if check_digit_9 != int(regon[8]):
        return False
    if len(regon) == 14:
        weights_14 = [2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8]
        checksum_14 = sum(int(regon[i]) * weights_14[i] for i in range(13))
        check_digit_14 = checksum_14 % 11
        if check_digit_14 == 10:
            check_digit_14 = 0
        if check_digit_14 != int(regon[13]):
            return False
    return True


def validate_pesel(pesel: str) -> bool:
    """Sprawdza poprawnosc PESEL."""
    pesel = pesel.replace("-", "").replace(" ", "")
    if len(pesel) != 11 or not pesel.isdigit():
        return False
    weights = [1, 3, 7, 9, 1, 3, 7, 9, 1, 3]
    checksum = sum(int(pesel[i]) * weights[i] for i in range(10))
    return (10 - (checksum % 10)) % 10 == int(pesel[10])


def validate_id_card(id_card: str) -> bool:
    """Sprawdza poprawnosc dowodu osobistego (3 litery + 6 cyfr)."""
    id_card = id_card.replace(" ", "").replace("-", "").upper()
    if len(id_card) != 9:
        return False
    letters = id_card[:3]
    digits = id_card[3:]
    if not (letters.isalpha() and digits.isdigit()):
        return False

    # Przeliczenie liter na wartości A=10 ... Z=35
    def char_value(c: str) -> int:
        return ord(c) - ord("A") + 10

    values = [char_value(letters[0]), char_value(letters[1]), char_value(letters[2]),
              int(digits[0]), int(digits[1]), int(digits[2]), int(digits[3]), int(digits[4]), int(digits[5])]

    weights = [7, 3, 1, 9, 7, 3, 1, 7, 3]
    checksum = sum(values[i] * weights[i] for i in range(9))
    return (checksum % 10) == 0


def validate_iban(iban: str) -> bool:
    """Sprawdza poprawnosc IBAN/NRB metoda mod97."""
    iban = iban.replace(" ", "").upper()
    if not iban.startswith("PL"):
        iban = "PL" + iban
    if len(iban) != 28:
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = ""
    for ch in rearranged:
        if ch.isdigit():
            numeric += ch
        elif ch.isalpha():
            numeric += str(ord(ch) - ord("A") + 10)
        else:
            return False
    return int(numeric) % 97 == 1
