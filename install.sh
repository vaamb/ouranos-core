#!/bin/bash

echo "Installing Ouranos"

# Create ouranos dir and sub dirs
mkdir "ouranos"; cd "ouranos"
OURANOS_DIR=$PWD

python3 -m venv python_venv
source python_venv/bin/activate

mkdir "bin"; cd "bin"

# Get Ouranos and install the package
git clone --branch stable https://gitlab.com/gaia/ouranos.git "ouranos_core"; cd "ouranos_core"
pip install --upgrade pip setuptools wheel
pip install -e .
deactivate

# Make Ouranos utility scripts easily available
cp main.py $OURANOS_DIR/main.py
cp start.sh $OURANOS_DIR/start.sh
cp stop.sh $OURANOS_DIR/stop.sh
cp update.sh $OURANOS_DIR/update.sh

cd "$OURANOS_DIR"
chmod +x "start.sh"
chmod +x "stop.sh"
chmod +x "update.sh"

# Copy vars and utility function to bash_profile
echo "Exporting "
if [ $(grep -ic "^OURANOS_DIR" $HOME/.bash_profile) -eq 0 ]; then
  echo "
# Ouranos root directory
OURANOS_DIR=$OURANOS_DIR" >> $HOME/.bash_profile;
fi

if [ $(grep -ic "^ouranos()" $HOME/.bash_profile) -eq 0 ]; then
  echo "
# Ouranos utility function to start and stop the main application
ouranos() {
  case \$1 in
    start) nohup \$OURANOS_DIR/start.sh &> \$OURANOS_DIR/.logs/nohup.out & ;;
    stop) \$OURANOS_DIR/stop.sh ;;
    log) tail \$OURANOS_DIR/.logs/nohup.out ;;
    update) bash \$OURANOS_DIR/ouranos_update.sh ;;
    *) echo 'Need an argument in \'start\', \'stop\', \'log\' or \'update\'' ;;
  esac
}
complete -W 'start stop log update' ouranos
" >> $HOME/.bash_profile;
fi

echo "Ouranos installed. To run it, either use \`ouranos start\` or go to the ouranos directory, activate the virtual environment and run \`python main.py\`"

exit