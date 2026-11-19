#!/usr/bin/env bash
# Dev container setup: local Postgres, Python environment and schema for the Document Engine.
# Run after every container recreation:   bash scripts/dev_up.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# 1. Install Postgres if missing
if ! command -v pg_ctlcluster >/dev/null 2>&1; then
  echo "installing postgresql..."
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql >/dev/null
fi

# 2. Start it if not running
if ! pg_isready -q -h 127.0.0.1; then
  echo "starting postgresql..."
  sudo service postgresql start >/dev/null
  for _ in $(seq 1 20); do pg_isready -q -h 127.0.0.1 && break; sleep 0.5; done
fi

# 3. Create the role and database if missing
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='docengine'" | grep -q 1; then
  sudo -u postgres psql -qc "CREATE USER docengine WITH PASSWORD 'docengine';"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='docengine'" | grep -q 1; then
  sudo -u postgres psql -qc "CREATE DATABASE docengine OWNER docengine;"
fi

# 4. Python environment
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
pip install -q -r requirements.txt

# 5. Config for local development (kept out of git)
if [ ! -f config.yaml ]; then
  sed -e 's#host: "FILL-IN".*#host: "127.0.0.1"#' -e 's#dbname: "FILL-IN"#dbname: "docengine"#' \
      -e 's#user: "FILL-IN"#user: "docengine"#' -e 's#sslmode: require#sslmode: prefer#' \
      config.example.yaml > config.yaml
  echo "created config.yaml: set gateway.base_url in it"
fi

# 6. Schema and sample material (both safe to run again)
export PGPASSWORD=docengine
python -m doc_engine db init
python -m doc_engine samples

echo
echo "ready. In your shell, still run:"
echo "  . .venv/bin/activate"
echo "  export PGPASSWORD=docengine"
echo "  export DATABRICKS_TOKEN='dapi...'"
echo "then:  python -m doc_engine preflight   and   python -m doc_engine serve"
