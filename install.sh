#!/bin/bash

echo "Installing Ouranos"
ORIGIN=$PWD

# Create ouranos
mkdir ouranos; cd ouranos
export OURANOS_DIR=$PWD

python3 -m venv venv
source venv/bin/activate

# Get Ouranos and install the package
mkdir bin; cd bin
git clone --branch stable https://gitlab.com/gaia/ouranos.git ouranos_core; cd ouranos_core
pip install -r requirements.txt
pip install -e .
deactivate

# Make Ouranos cli and utility scripts easily available
cp update.sh $OURANOS_DIR/update.sh

ouranos() {
  source $OURANOS_DIR/venv/bin/activate
  python -m ouranos "$@"
  deactivate
}

export -f ouranos

cd $ORIGIN
echo "Ouranos installed. To run it, either use \`ouranos\` or \`python -m ouranos\` within your venv"
