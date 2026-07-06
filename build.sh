#!/bin/bash
VER=$(date +%Y%m%d%H)
echo "Build version: $VER"
cp index.js index.${VER}.js
cp api.js api.${VER}.js
for html in *.html; do
  sed -i "s|index\\.[0-9]*\\.js|index.${VER}.js|g" $html
  sed -i "s|api\\.[0-9]*\\.js|api.${VER}.js|g" $html
done
echo "Done: $VER"
