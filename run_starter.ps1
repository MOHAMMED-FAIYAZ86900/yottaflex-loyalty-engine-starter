python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m loyalty.cli --customers 100 --orders 500 --seed 20261022
pytest -q
