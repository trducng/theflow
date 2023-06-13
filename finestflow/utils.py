import importlib
from pathlib import Path
from typing import Optional


FINESTFLOW_DIR = ".finestflow"


def project_root(loc: Optional[str]) -> Optional[Path]:
    """Get the root directory of the project (contains .git/)

    Args:
        loc: the location to start searching for the root directory. If None,
            assume the current working directory

    Returns:
        the root directory of the project, or None if not found
    """
    if loc is None:
        loc = Path.cwd()
    loc = Path(loc)
    while loc != loc.parent:
        if (loc / ".git").exists():
            return loc
        loc = loc.parent

    return None


def get_finestflow_path(loc: Optional[str]) -> Optional[Path]:
    """Get the finestflow directory (contains .finestflow/)

    Args:
        loc: the location to start searching for the finestflow directory. If None,
            assume the current working directory

    Returns:
        the finestflow directory, or None if not found
    """
    loc = Path.cwd() if loc is None else Path(loc)
    while loc != loc.parent:
        if (loc / FINESTFLOW_DIR).exists():
            return loc / FINESTFLOW_DIR
        loc = loc.parent

    return None


def get_or_create_finestflow_path(loc: Optional[str]=None) -> Path:
    """Get the finestflow directory (.finestflow/) or create it if not exists

    It travels up the directory tree until it finds the finestflow directory. If not
    found, it creates the finestflow directory in the project root folder. If there
    isn't project root folder, it creates the finestflow directory in the current
    working directory.

    Args:
        loc: the location to start searching for the finestflow directory. If None,
            assume the current working directory

    Returns:
        the finestflow directory
    """
    if loc is None:
        loc = Path.cwd()
    loc = Path(loc)
    finestflow_path = get_finestflow_path(loc)
    if finestflow_path is not None:
        return finestflow_path

    project_root_path = project_root(loc)
    if project_root_path is None:
        finestflow_path = Path.cwd() / FINESTFLOW_DIR
    else:
        finestflow_path = project_root_path / FINESTFLOW_DIR

    finestflow_path.mkdir(exist_ok=True, parents=True)
    return finestflow_path


def import_dotted_string(dotted_string):
    """Import a dotted string

    Args:
        dotted_string: the dotted string to import

    Returns:
        the imported object
    """
    # TODO: cached import
    module_name, obj_name = dotted_string.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, obj_name)