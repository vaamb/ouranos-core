#!/bin/bash

if pgrep -x "ouranos" > /dev/null; then
  pkill -15 "ouranos"
  rm $OURANOS_DIR/logs/stdout
else
  echo "No instance of Ouranos currently running"
fi
