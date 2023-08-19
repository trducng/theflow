import importlib
import re
from pathlib import Path
from typing import Optional, Union


FINESTFLOW_DIR = ".finestflow"


def project_root(loc: Optional[Union[str, Path]]) -> Optional[Path]:
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


def get_finestflow_path(loc: Optional[Union[str, Path]]) -> Optional[Path]:
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


def is_name_matched(name: str, pattern: str) -> bool:
    """Check if a name matches a pattern

    This method matches simple pattern with wildcard character "*". For example, the
    pattern "a.*.b" matches "a.c.b" but not "a.b.c.b".
    
    Args:
        name: the name to check
        pattern: the pattern to match
    
    Returns:
        True if the name matches the pattern, False otherwise
    """
    pattern_parts: list[str] = [re.escape(part) for part in pattern.split("*")]
    regex_pattern: str = r'^' + r'[^.]+'.join(pattern_parts) + r'$'
    return re.findall(regex_pattern, name) != []


def is_parent_of_child(parent: str, child: str) -> bool:
    """Check if a name is a direct parent of another name

    Example:
        >> is_parent_of_child(".main.pipeline_A1", ".main.pipeline_A1.*")
        True
        >> is_parent_of_child(".main.pipeline_A1", ".main.pipeline_A1.pipeline_B1")
        True
        >> is_parent_of_child(".main.pipeline_A1", ".main.pipeline_A2")
        False

    Args:
        parent: the parent name
        child: the child name. The child can be a wildcard pattern
        
    Returns:
        True if the parent is a parent of the child, False otherwise
    """
    pattern = ".".join(child.split(".")[:-1])
    return is_name_matched(parent, pattern)


def reindent_docstring(docin: str) -> str:
    """Remove beginning whitespace in a docstring"""
    if not docin:
        return ""

    whitespaces = re.findall(r"\n[ \t]+", docin)
    if whitespaces:
        min_whitespace = min(whitespaces)[1:]
        lines = []
        for line in docin.splitlines():
            if line.startswith(min_whitespace):
                line = line[len(min_whitespace):]
            lines.append(line)
        docin = "\n".join(lines).strip()
    return docin


if __name__ == "__main__":
    names = [
        "",
        ".main",
        ".main.pipeline_A1"
        ".main.pipeline_A1.pipeline_B1",
        ".main.pipeline_A1.pipeline_B1.pipeline_C1",
        ".main.pipeline_A1.pipeline_B1.pipeline_C1.step_a",
        ".main.pipeline_A1.pipeline_B1.pipeline_C1.step_b",
        ".main.pipeline_A1.pipeline_B1.pipeline_C1.step_c",
        ".main.pipeline_A1.pipeline_B2",
        ".main.pipeline_A1.pipeline_B2.pipeline_C2",
        ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a",
        ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_b",
        ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_c",
        ".main.pipeline_A2",
        ".main.pipeline_A2.pipeline_B1",
        ".main.pipeline_A2.pipeline_B1.pipeline_C1",
        ".main.pipeline_A2.pipeline_B1.pipeline_C1.step_a",
        ".main.pipeline_A2.pipeline_B1.pipeline_C1.step_b",
        ".main.pipeline_A2.pipeline_B1.pipeline_C1.step_c",
        ".main.pipeline_A2.pipeline_B2",
        ".main.pipeline_A2.pipeline_B2.pipeline_C2",
        ".main.pipeline_A2.pipeline_B2.pipeline_C2.step_a",
        ".main.pipeline_A2.pipeline_B2.pipeline_C2.step_b",
        ".main.pipeline_A2.pipeline_B2.pipeline_C2.step_c",
        ".main.next_step",
    ]

    # pattern  = ".main.*.p*.*.step_a"
    # pattern = ".main.*.*.pipeline_C1"
    # pattern = ".main.pipeline_A2"
    pattern = ".*.pipeline*"
    # for name in names:
    #     if is_name_matched(name, pattern):
    #         print(name)

    for name in names:
        if is_parent_of_child(name, pattern):
            print(name, "is parent of", pattern)
