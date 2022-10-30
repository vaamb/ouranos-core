#!/bin/bash

echo "Starting Ouranos"

DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

cd $DIR

if pgrep -x "ouranos" > /dev/null; then
  pkill -15 "ouranos"
fi

source venv/bin/activate

python3 main.py &
