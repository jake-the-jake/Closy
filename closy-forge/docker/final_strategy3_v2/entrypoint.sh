#!/bin/sh
set -eu
umask 077
exec python /app/runner.py
