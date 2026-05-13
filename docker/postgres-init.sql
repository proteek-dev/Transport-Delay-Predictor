-- Bootstrap PostGIS once on volume creation. The image already ships the
-- extension binaries; we just make sure the extension is enabled in our DB.
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
