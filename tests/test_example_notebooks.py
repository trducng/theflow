import tempfile
from pathlib import Path
from typing import Union

import papermill as pm
import pytest

EXAMPLE_FOLDER = Path(__file__).parent.parent / "examples"


@pytest.mark.parametrize(
    "notebook_path",
    [
        Path(EXAMPLE_FOLDER, "01_10-minutes-quick-start.ipynb"),
        Path(EXAMPLE_FOLDER, "02_params-and-nodes.ipynb"),
        Path(EXAMPLE_FOLDER, "03_introspection.ipynb"),
        Path(EXAMPLE_FOLDER, "04_save_and_load.ipynb"),
        Path(EXAMPLE_FOLDER, "05_context.ipynb"),
        Path(EXAMPLE_FOLDER, "06_multiprocessing.ipynb"),
    ],
)
def test_execute_all_notebooks(notebook_path: Union[Path, str]):
    notebook_path = Path(notebook_path)
    output_path = tempfile.mkstemp(
        suffix=notebook_path.suffix,
        prefix=notebook_path.stem,
    )[1]
    pm.execute_notebook(notebook_path, output_path=output_path)
