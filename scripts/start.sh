#!/bin/bash

exec </dev/null 1>"$OURANOS_DIR/logs/stdout" 2>&1

if pgrep -x "ouranos" > /dev/null; then
  echo "An instance of Ouranos is already running please stop it before starting another one"
else
  echo "Starting Ouranos";
  cd "$OURANOS_DIR" || echo "\$OURANOS_DIR is not set, exiting" exit
  source python_venv/bin/activate
  python3 -m ouranos
fi
