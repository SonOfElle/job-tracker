.PHONY: help up down ps logs dev-db api ui migrate migrate-new migrate-prod deploy backup

# Default target — shows available commands.
help:
	@echo "Job Tracker — common commands"
	@echo ""
	@echo "Dev (Windows, bare uvicorn + streamlit):"
	@echo "  make dev-db        Start only the Postgres container"
	@echo "  make api           Run uvicorn on 127.0.0.1:8050"
	@echo "  make ui            Run Streamlit on 127.0.0.1:8501 pointing at :8050"
	@echo ""
	@echo "Migrations:"
	@echo "  make migrate       alembic upgrade head (local)"
	@echo "  make migrate-new MESSAGE='add foo'   autogenerate a migration"
	@echo "  make migrate-prod  one-off container migration on the server"
	@echo ""
	@echo "Full stack:"
	@echo "  make up            docker compose up -d (all services)"
	@echo "  make down          docker compose down"
	@echo "  make ps            docker compose ps"
	@echo "  make logs          docker compose logs -f"
	@echo ""
	@echo "Server:"
	@echo "  make deploy        git pull + rebuild + up (run on the server)"
	@echo "  make backup        run the backup script (server)"

# ---- Dev ----------------------------------------------------------------

dev-db:
	docker compose up -d db

api:
	uvicorn app.main:app --host 127.0.0.1 --port 8050

ui:
	API_BASE_URL=http://127.0.0.1:8050 streamlit run ui/app.py --server.port 8501

# ---- Migrations ---------------------------------------------------------

migrate:
	alembic upgrade head

migrate-new:
	@if [ -z "$(MESSAGE)" ]; then echo "Usage: make migrate-new MESSAGE='description'"; exit 1; fi
	alembic revision --autogenerate -m "$(MESSAGE)"

migrate-prod:
	docker compose run --rm --no-deps api alembic upgrade head

# ---- Full stack ---------------------------------------------------------

up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f

# ---- Server -------------------------------------------------------------

deploy:
	git pull
	docker compose build
	docker compose up -d
	docker compose ps

backup:
	~/job-tracker-backup.sh
	tail -4 /mnt/RedArchive_Cold/Backups/job-tracker/backup.log