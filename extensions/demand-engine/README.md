# Demand Engine

Pure Python maintenance-spare demand calculation package. It has no FastAPI, SQLAlchemy or database dependency.

```powershell
cd extensions\demand-engine
python -m pip install -e .
python -m pytest -v
```

CLI:

```powershell
demand-engine calculate --input scenario.json --output result.json
```

Supported models: exponential/Poisson, Weibull conditional failure and renewal approximation, binomial, negative binomial, empirical moment matching, adaptive Monte Carlo and analytical/Monte Carlo comparison.
