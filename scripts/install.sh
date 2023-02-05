#!/bin/bash

echo "Installing Ouranos"

# Create ouranos dir and sub dirs
mkdir "ouranos"; cd "ouranos"
OURANOS_DIR=$PWD

echo "Creating a python virtual environment"
python3 -m venv python_venv
source python_venv/bin/activate

mkdir "logs"
mkdir "scripts"
mkdir "lib"; cd "lib"

# Get Ouranos and install the package
echo "Getting Ouranos repository"
git clone --branch stable https://gitlab.com/eupla/ouranos.git "ouranos_core"; cd "ouranos_core"
echo "Installing Ouranos and its dependencies"
pip install --upgrade pip setuptools wheel
pip install -e .
deactivate

# Make Ouranos utility scripts easily available
cp main.py $OURANOS_DIR/scripts/main.py
cp scripts/ $OURANOS_DIR/scripts/

cd "$OURANOS_DIR/scripts/"
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
    start) nohup \$OURANOS_DIR/scripts/start.sh &> \$OURANOS_DIR/logs/nohup.out & ;;
    stop) \$OURANOS_DIR/scripts/stop.sh ;;
    log) tail \$OURANOS_DIR/logs/nohup.out ;;
    update) bash \$OURANOS_DIR/scripts/update.sh ;;
    *) echo 'Need an argument in start, stop, log or update' ;;
  esac
}
complete -W 'start stop log update' ouranos
" >> $HOME/.bash_profile;
fi

echo "Ouranos installed. To run it, either use \`ouranos start\` or go to the ouranos directory, activate the virtual environment and run \`python main.py\`"

exit