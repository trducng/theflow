# Contribute to theflow

## Installation

1. Fork and clone the repo.
2. Create a Python virtual environment with virtualenv, conda,...
3. Install theflow in editable dev mode: `pip install -e ".[dev]"`
4. Activate pre-commit: `pre-commit install`

## Test

After development, you should add and check the tests:

```shell
$ coverage run -m pytest tests
```

## PR

Please make PR from your fork to this repository.
