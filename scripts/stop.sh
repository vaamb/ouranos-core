#!/bin/bash

if [ pgrep -x "ouranos" > /dev/null; ] then
  pkill -15 "ouranos"
else
  echo "No instance of Ouranos currently running"
fi
