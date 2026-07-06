#!/bin/bash
VER=2026070703
echo "Build version: "
cp index.js index..js
cp api.js api..js
for html in *.html; do
    sed -i "s|index\\.[0-9]*\\.js|index..js|g" 
    sed -i "s|api\\.[0-9]*\\.js|api..js|g" 
done
echo "Done: "
