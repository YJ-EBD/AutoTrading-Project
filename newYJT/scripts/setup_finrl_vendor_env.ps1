$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root "runtime\\finrl_venv"
$python = Join-Path $venv "Scripts\\python.exe"
$pip = Join-Path $venv "Scripts\\pip.exe"
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:OPENBLAS_NUM_THREADS = "1"
$env:OMP_NUM_THREADS = "1"

if (-not (Test-Path $venv)) {
    python -m venv $venv
}

Set-Location $root
& $python -m pip install --upgrade pip setuptools wheel

$packages = @(
    "numpy>=1.24.0",
    "pandas>=2.0.0",
    "scikit-learn>=1.3.0",
    "scipy>=1.11.0",
    "lightgbm>=4.0.0",
    "xgboost>=2.0.0",
    "matplotlib>=3.7.0",
    "plotly>=5.15.0",
    "seaborn>=0.12.0",
    "streamlit>=1.28.0",
    "yfinance>=0.2.0",
    "requests>=2.31.0",
    "python-dotenv>=1.0.0",
    "alpaca-py>=0.13.0",
    "openai>=1.40.0",
    "pandas-market-calendars>=4.3.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "sqlalchemy>=2.0.0",
    "typing-extensions>=4.8.0",
    "lxml>=4.9.0",
    "PyYAML>=6.0.0",
    "finnhub-python>=2.4.19"
)

foreach ($package in $packages) {
    & $pip install $package
}

& $pip install -e vendor\FinRL-Trading --no-deps
