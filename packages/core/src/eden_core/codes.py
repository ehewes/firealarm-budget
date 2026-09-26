"""Session codes, in the `EM-7K2Q9X4M` shape from 0001_init.sql.

A code is a read-only capability: whoever has it can read the session's context,
which is exactly what lets Grok read it. Eight characters from a 30-letter
alphabet is about 39 bits; with sessions expiring after a day and the API rate
limited, guessing one is not a practical attack. The alphabet drops 0/O, 1/I/L
and U so a code survives being read aloud or retyped.
"""

import re
import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"
_CODE = re.compile(r"^EM-[" + ALPHABET + r"]{8}$")


def new_session_code() -> str:
    return "EM-" + "".join(secrets.choice(ALPHABET) for _ in range(8))


def is_session_code(value: str) -> bool:
    return bool(_CODE.match(value))
