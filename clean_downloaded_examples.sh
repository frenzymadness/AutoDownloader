#!/bin/bash

# Simple script to interactively remove all content downloaded when testing
# configuration files from examples/ directory

for EX_PATH in `cat examples/*.autodlrc | grep "\[PATH\]" | sed "s/.*\[PATH\]\(.*\)\[\/PATH\]/\1/"`
do
    rm -rvi `eval echo $EX_PATH`
done
