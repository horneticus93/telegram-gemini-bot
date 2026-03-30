-- Load Apache AGE extension (already created in 00-create-extension-age.sql)
CREATE EXTENSION IF NOT EXISTS vector;
LOAD 'age';
SET search_path = ag_catalog, "$user", public;
SELECT create_graph('memory');
