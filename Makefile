PY_FILES := $(wildcard src/**/**/*.py)

format:
	ruff format $(PY_FILES)

lint:
	ruff check $(PY_FILES)

fix:
	ruff check $(PY_FILES) --fix

unsafe-fix:
	ruff check --fix --unsafe-fixes $(PY_FILES)

uv_lint:
	uv run --with=ruff ruff check . --fix
	uv run --with=black black .

ruff_version:
	ruff --version

install_ruff:
	uv pip install ruff

view_lines:
	loc src/

clean:
	@echo "Cleaning directory..."
	@find . \( -name "__pycache__" -o -name ".DS_Store" -o -name ".ruff_cache" \) -exec rm -r {} +
	@echo "Done."