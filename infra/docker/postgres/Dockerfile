# PostgreSQL 16 + pgvector + PostGIS (pg_trgm, btree_gist and citext ship with contrib).
FROM pgvector/pgvector:pg16-bookworm
# PostGIS from apt is built for the newest 16.x, so upgrade the server in the same step to keep them matched.
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16 postgresql-16-postgis-3 \
 && rm -rf /var/lib/apt/lists/*
