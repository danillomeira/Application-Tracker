-- Executado só na primeira inicialização do volume.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE DATABASE tracker_test OWNER tracker;
\connect tracker_test
CREATE EXTENSION IF NOT EXISTS vector;
