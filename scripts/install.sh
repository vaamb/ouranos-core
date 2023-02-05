#!/bin/bash

echo "Installing Ouranos"

# Create ouranos dir and sub dirs
mkdir -p "ouranos"; cd "ouranos"
OURANOS_DIR=$PWD

if [ ! -d "python_venv" ]; then
  echo "Creating a python virtual environment"
  python3 -m venv python_venv
fi
source python_venv/bin/activate

mkdir -p "logs"
mkdir -p "scripts"
mkdir -p "lib"; cd "lib"

# Get Ouranos and install the package
if [ ! -d "ouranos_core" ]; then
  echo "Getting Ouranos repository"
  git clone --branch installer https://gitlab.com/eupla/ouranos.git "ouranos_core" > /dev/null
  if [ $? = 0 ] ; then
    cd "ouranos_core"
  else
    echo "Failed to get Ouranos repository from git";
    exit 2
  fi
  echo "Updating pip setuptools and wheel"
  pip install --upgrade pip setuptools wheel
else
  echo "Detecting an existing installation, you should update it if needed. Stopping"
  exit 1
fi
echo "Installing Ouranos and its dependencies"
pip install -e .
deactivate

# Make Ouranos scripts easily available
cp -r scripts/ $OURANOS_DIR/

cd "$OURANOS_DIR/scripts/"
chmod +x start.sh stop.sh update.sh

# Copy vars and utility function to bash_profile
echo "Exporting Ouranos variables to .bash_profile"

if [ ! -f $HOME/.bash_profile ]; then
  touch $HOME/.bash_profile
fi

if [ $(grep -ic "^OURANOS_DIR" $HOME/.bash_profile) -eq 0 ]; then
  echo "
# Ouranos root directory
export OURANOS_DIR=$OURANOS_DIR" >> $HOME/.bash_profile;
fi

if [ $(grep -ic "^ouranos()" $HOME/.bash_profile) -eq 0 ]; then
  echo "
# Ouranos utility function to start and stop the main application
ouranos() {
  case \$1 in
    start) nohup \$OURANOS_DIR/scripts/start.sh &> \$OURANOS_DIR/logs/nohup.out & ;;
    stop) \$OURANOS_DIR/scripts/stop.sh ;;
    stdout) tail \$OURANOS_DIR/logs/nohup.out ;;
    update) bash \$OURANOS_DIR/scripts/update.sh ;;
    *) echo 'Need an argument in start, stop, stdout or update' ;;
  esac
}
complete -W 'start stop stdout update' ouranos
" >> $HOME/.bash_profile;
fi

source $HOME/.bash_profile

echo "Ouranos installed. To run it, either use \`ouranos start\` or go to the ouranos directory, activate the virtual environment and run \`python main.py\`"

exit