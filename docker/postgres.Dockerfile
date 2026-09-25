FROM postgres:17-alpine
COPY --chmod=644 docker/init-databases.sh /docker-entrypoint-initdb.d/01-delta.sh
