#!/bin/sh
chown -R appuser:appuser /app/data
exec gosu appuser "$@"
