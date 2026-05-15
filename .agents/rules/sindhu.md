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
