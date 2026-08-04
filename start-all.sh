#!/bin/bash
node server.js &
node CT/server_traditional.js &
wait
