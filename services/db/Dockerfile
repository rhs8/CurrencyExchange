FROM timescale/timescaledb:latest-pg16

# Bake schema into the image so hosts (Railway, etc.) do not need a bind-mounted ./db/init volume.
COPY db/init/ /docker-entrypoint-initdb.d/
