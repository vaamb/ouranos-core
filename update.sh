#!/bin/bash

echo "Updating Ouranos"
ORIGIN=$PWD

# Go to ouranos dir
cd "$OURANOS_DIR/bin" ||  { echo "Cannot go to \`OURANOS_DIR\`/bin did you install Ouranos using the \`install.sh\` script?"; exit; }

for dir in */ ; do
  (
    cd $dir;
    LOCAL_HASH=$"git rev-parse stable"
    ORIGIN_HASH=$"git rev-parse origin/stable"

    if $LOCAL_HASH != $ORIGIN_HASH; then
      git pull --recurse-submodules
    fi
  )
done

cd "$ORIGIN"
echo "Ouranos update. To run it, either use \`ouranos\` or \`python -m ouranos\` within your venv"

exit