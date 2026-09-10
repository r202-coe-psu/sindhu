---
trigger: always_on
---

# Project Rules (sindhu)

- **Debug Scripts:** Any debug scripts must be created exclusively in the `.agents/debug` directory (do not create them at the root or other directories).
- **Running Scripts:** Always run Python scripts using the command `poetry run python <script>`.
- **Project Stack:**
  - **Backend:** FastAPI, Flask
  - **Database ODM:** Beanie (MongoDB)
  - **Frontend:** Brython, HTML Templates
  - **Dependency Management:** Poetry
  - **Code Formatting:** Black
- **Language:** Communicate and explain code in English, as requested.
- **Commenting:** Always use {# comment #} instead of {# #} and // in .html file 
- **Schema & MageAI Compatibility (Python 3.10):**
  - MageAI runs on **Python 3.10**, whereas the main app runs on Python 3.13. All shared code, schemas (`sindhu/schemas/`), and models (`sindhu/models/`) mounted into MageAI must remain strictly compatible with Python 3.10.
  - **Generics in Schemas & Models:** Always use `typing` module collections (`Dict`, `List`, `Optional`, `Set`, `Tuple`) instead of PEP 585 built-in type hints (`dict[...]`, `list[...]`). This prevents Beanie 2.2.0 from raising `TypeError: issubclass() arg 1 must be a class` due to `types.GenericAlias` type-check quirks in Python 3.10.
  - **Enums:** Do not import `StrEnum` directly from `enum` (only available in Python 3.11+). Use `class MyEnum(str, Enum):` or import with backwards-compatible fallback.
  - **Typing Extensions:** Use `from typing_extensions import Self` instead of `from typing import Self`.