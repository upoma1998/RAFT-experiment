# Original RAFT Paper Phase-I Reproduction

## Purpose

This directory records my attempt to reproduce Phase I of the paper:

"The Effects of Computational Resources on Flaky Tests"

The reproduction is kept separate from the current RAFT-experiment implementation.

## Repository provenance

Original repository:
https://github.com/jiajuwang/RAFT-experiment

My fork:
https://github.com/upoma1998/RAFT-experiment

Working branch:
reproduce-original-paper-phase1

The original repository is configured as the `upstream` remote with push
disabled. All changes are pushed only to my fork through `origin`.

## Important distinction

The current RAFT-experiment repository has evolved after the original paper
and does not implement the published Phase-I experiment exactly.

Therefore, this branch first reconstructs the experimental methodology
reported in the original paper before conducting any new research.

## Original Phase-I design reported in the paper

- 52 projects
  - 30 Java
  - 10 JavaScript
  - 12 Python
- Baseline + 15 throttling configurations
- Resources investigated:
  - CPU
  - Memory
  - Disk
  - Network
- 300 executions of each project under every configuration
- Baseline machine configuration:
  - 4 CPU cores
  - 16 GiB RAM
- Test suites executed in Docker containers
- Resource constraints applied through Docker/Linux resource controls
- Statistical RAFT classification based on failure-rate differences

## Evidence organization

commands/
    Exact commands and scripts used.

logs/
    Raw terminal and execution logs.

results/
    Raw and processed experiment results.

metadata/
    Git, host, Docker, and environment information.

