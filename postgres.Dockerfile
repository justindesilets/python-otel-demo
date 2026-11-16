# syntax=docker/dockerfile:1
FROM postgres:18.7
COPY ./configs/postgres/seed.sql /docker-entrypoint-initdb.d/
