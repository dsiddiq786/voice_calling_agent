#!/bin/zsh

PORT_PIDS=(${(f)"$(lsof -tiTCP:8010 -sTCP:LISTEN 2>/dev/null)"})
if (( ${#PORT_PIDS[@]} )); then
  kill $PORT_PIDS
  echo "NomNosh server stopped."
else
  echo "NomNosh server was not running."
fi
sleep 2
