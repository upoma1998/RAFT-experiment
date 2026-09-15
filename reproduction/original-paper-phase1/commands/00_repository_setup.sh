#!/usr/bin/env bash

# Repository used:
# https://github.com/upoma1998/RAFT-experiment
#
# Original upstream:
# https://github.com/jiajuwang/RAFT-experiment

# Clone performed earlier:
git clone https://github.com/upoma1998/RAFT-experiment.git

cd RAFT-experiment

# Add the original repository as read-only upstream.
git remote add upstream https://github.com/jiajuwang/RAFT-experiment.git
git remote set-url --push upstream DISABLED

# Create a separate branch for reproducing the original paper.
git switch -c reproduce-original-paper-phase1

# Push only to my fork.
git push -u origin reproduce-original-paper-phase1

# Verification commands.
git remote -v
git branch -vv
git status
git log --oneline -5
