#!/bin/bash

echo "Updating Ouranos"

# Go to ouranos dir
cd "$OURANOS_DIR" || { echo "Cannot go to \`OURANOS_DIR\`/lib did you install Ouranos using the \`install.sh\` script?"; exit; }

source python_venv/bin/activate

cd "/lib"
for dir in */ ; do
  (
    cd $dir;
    LOCAL_HASH=$"git rev-parse stable"
    ORIGIN_HASH=$"git rev-parse origin/stable"

    if [ $LOCAL_HASH != $ORIGIN_HASH ]; then
      git pull --recurse-submodules
      pip install -e .
    fi
  )
done

deactivate

echo "Ouranos updated. To run it, either use \`ouranos start\` or go to the ouranos directory, activate the virtual environment and run \`python main.py\` or \`python -m ouranos\`"

exit
