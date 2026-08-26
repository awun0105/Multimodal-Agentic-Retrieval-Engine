UV ?= uv
PYTHON_VERSION ?= 3.10
VENV := .venv
PYTHON := $(VENV)/bin/python

.PHONY: run dev setup clean

run: setup
	@. $(VENV)/bin/activate && exec python app.py

dev: setup
	@. $(VENV)/bin/activate && exec $(VENV)/bin/gradio app.py

setup:
	@command -v $(UV) >/dev/null 2>&1 || { echo "Error: uv is not installed or not on PATH." >&2; exit 1; }
	@if [ ! -x "$(PYTHON)" ]; then \
		echo "Creating uv virtual environment..."; \
		$(UV) venv --python $(PYTHON_VERSION) $(VENV); \
	fi
	@echo "Checking Python requirements..."
	@$(UV) pip install --python "$(PYTHON)" -r requirements.txt

clean:
	@rm -rf "$(VENV)"
	@echo "Removed $(VENV)."
