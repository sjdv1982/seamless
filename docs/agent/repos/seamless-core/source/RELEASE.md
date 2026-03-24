# Release `seamless-core` to PyPI

## One-time setup

- Ensure you have PyPI maintainer access for `seamless-core`.
- Install build tooling:

```bash
python -m pip install --upgrade build twine
```

## Build

```bash
python -m build
```

This creates artifacts in `dist/`.

## Validate

```bash
python -m twine check dist/*
```

## Upload

Test PyPI:

```bash
python -m twine upload --repository testpypi dist/*
```

Production PyPI:

```bash
python -m twine upload dist/*
```
