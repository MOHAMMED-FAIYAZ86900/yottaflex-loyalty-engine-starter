#!/usr/bin/env bash
set -e
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m loyalty.cli --customers 100 --orders 500 --seed 20261022
pytest -q
