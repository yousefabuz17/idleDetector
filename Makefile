PY_FILES := $(wildcard src/**/**/*.py)

format:
	uv run ruff format $(PY_FILES)

lint:
	uv run ruff check $(PY_FILES)

fix:
	uv run ruff check $(PY_FILES) --fix

unsafe-fix:
	uv run ruff check --fix --unsafe-fixes $(PY_FILES)

cache-clean:
	uv cache clean

uv_lint:
	uv run --with=ruff ruff check . --fix
	uv run --with=black black .

ruff_version:
	uv run ruff --version

install_ruff:
	uv pip install ruff

view_lines:
	loc src/

clean:
	@echo "Cleaning directory..."
	@find . \( -name "__pycache__" -o -name ".DS_Store" -o -name ".ruff_cache" \) -exec rm -r {} +
	@echo "Done."