# Repository Guidelines

## Project structure

- `cli.py` dispatches commands. `indexing/pipeline.py` handles dataset discovery, previews, batch indexing, and verification.
- `indexing/masking.py` exposes `create_bird_mask(image)`. `indexing/features.py` exposes `extract_features(image, mask)`. Keep both usable with in-memory RGB images.
- `search/` prepares query images, ranks feature vectors, exports results, and evaluates retrieval.
- `sql/database.py` registers images and reads and writes features. Keep each mask path and its three feature vectors in the same transaction. The schema and example SQL queries sit alongside this module.
- Input JPGs live in `data/images/`, generated PNGs in `data/masks/`, model weights in `models/`, and run logs and previews in `runs/`. The reports in `docs/` describe the feature definitions.

## Local development

From the repository root in PowerShell, create the environment, install dependencies, and fetch the CPU model weights:

```powershell
py -3.14 -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements.txt
& $py cli.py setup-models
```

Run `& $py cli.py run --offline --limit 1 --preview --check-background` to inspect one segmentation and check that changing background pixels preserves the features.

For MySQL 8.0.17 or later, copy `.env.example` to `.env` on first setup and fill in local credentials. Run `& $py cli.py init-db` to create the schema, `& $py cli.py run` to process the dataset, and `& $py cli.py verify-db` to compare stored values with freshly extracted vectors. Keep credentials, datasets, weights, and run outputs out of Git.

## Coding style and tests

Use four-space indentation, `snake_case` for functions, and a leading underscore for private helpers. Follow the existing module style. The project has no configured formatter, linter, or coverage threshold.

Preserve the feature order and dimensions: color (640), texture (26), shape (12). Use small, deterministic arrays for regression tests in `tests/test_*.py`. Name methods `test_*` and run `& $py -m unittest discover -s tests -v`. For segmentation changes, also inspect the contour overlay around the beak, feet, and tail.

## Commits and pull requests

Git history contains only `first commit`. Use short, descriptive subjects such as `Fix GLCM diagonal pair selection`. In pull requests, describe the behavior change, list commands run, and link a related issue when applicable. Include a representative contour preview when mask boundaries change.
