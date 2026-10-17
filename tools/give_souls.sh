#!/bin/bash
# give_souls.sh [N] : DEV ONLY. Set the player's souls to N (default 999999999, the game's cap) through the agent
# command channel. Needs a dev agent build (tools/build_agent.sh without --release) and the game running.
export MSYS_NO_PATHCONV=1
P=com.remipelloux.gamenativecustom; G=CustomGames/DarkSoulsRemastered
adb shell "run-as $P sh -c 'echo souls ${1:-999999999} > $G/dsr_cmd.txt'"
sleep 1; adb shell "run-as $P grep 'souls' $G/dsr_agent.log" | tail -1
