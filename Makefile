.PHONY: build run test test-e2e dev-backend dev-frontend dev

install:
	cd react && npm install
	uv venv || true
	. .venv/bin/activate && uv pip install -e .[dev]

build:
	cd src-tauri && cargo build
	cd react && npm run build

run:
	cd src-tauri && cargo run

test:
	. .venv/bin/activate && pytest tests/ -m "not e2e"

test-e2e:
	. .venv/bin/activate && pytest tests/test_e2e_integration.py -v

dev-backend:
	. .venv/bin/activate && python harness/main.py internal backend-worker --host 127.0.0.1 --port 9100

dev-frontend:
	cd react && npm run dev &

dev:
	@echo "To run the app in dev mode, run 'make dev-backend' in one terminal and 'make dev-frontend' in another terminal. Then you can run 'make run' to launch the tauri app."
