#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=core_password="$CORE_DB_PASSWORD" --set=tasks_password="$TASKS_DB_PASSWORD" <<'SQL'
CREATE USER delta_core WITH PASSWORD :'core_password';
CREATE USER delta_tasks WITH PASSWORD :'tasks_password';
CREATE DATABASE delta_core OWNER delta_core;
CREATE DATABASE delta_tasks OWNER delta_tasks;
REVOKE CONNECT ON DATABASE delta_core FROM PUBLIC;
REVOKE CONNECT ON DATABASE delta_tasks FROM PUBLIC;
GRANT CONNECT ON DATABASE delta_core TO delta_core;
GRANT CONNECT ON DATABASE delta_tasks TO delta_tasks;
SQL
