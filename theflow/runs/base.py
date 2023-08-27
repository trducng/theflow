import pickle
import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from ..context import BaseContext


class RunStructure:
    """The structure of a run directory"""

    progress = "progress.pkl"
    input = "input.pkl"
    output = "output.pkl"
    config = "config.yaml"
    # kwargs = "kwargs.pkl" ----> Should consolidate with config.yaml? Plug-n-play
    # pipeline = "pipeline.yaml" ---> Should consolidate with config.yaml? Plug-n-play
    # pipeline_visualization = "pipeline_visualization.dot"
    # run_visualization = "run_visualization.dot"


class RunManager:
    def __init__(self, dir: str):
        self.dir: Path = Path(dir)

    def list(self) -> list:
        """List all runs"""
        import pandas as pd  # TODO: reimplement json_normalize

        output = []
        for each_dir in self.dir.iterdir():
            if not each_dir.is_dir():
                continue

            run_info = {"name": each_dir.name}
            with (each_dir / RunStructure.output).open("rb") as fi:
                run_info.update(
                    pd.json_normalize({"output": pickle.load(fi)}).to_dict(
                        orient="records"
                    )[0]
                )
            with (each_dir / RunStructure.input).open("rb") as fi:
                input_ = pickle.load(fi)
                input_ = {"input": {"args": input_["args"], **input_["kwargs"]}}
                run_info.update(pd.json_normalize(input_).to_dict(orient="records")[0])

            output.append(run_info)

        return output

    def get(self):
        pass

    def delete(self, name: str):
        """Delete a run base a name

        Args:
            name: the name of the run
        """
        shutil.rmtree(self.dir / name)


class RunTracker:
    """Define run-related methods to track the information in the run

    Args:
        context: the context to store the run information
        which_progress: the name of the progress to store the run information. Can be
            useful to track multiple progresses in the same run. Default to
            "__progress__" which refers to the current progress.
        config: the config of the run
    """

    def __init__(self, context: BaseContext, which_progress: str = "__progress__"):
        self._context = context

        self._config = None
        self._progress = which_progress
        self._context.create_local_context(self._progress, exist_ok=True)

    def log_progress(self, name: str, input: Any, output: Any, status: str = "run"):
        """Set the input and output of the step

        Args:
            name: name of the pipeline or step
            input: input of the step
            output: output of the step
            status: status of the step, one of "run", "rerun", "cached"
        """
        value = {"input": input, "output": output, "status": status}
        self._context.set(name, value, context=self._progress)

    def logs(self, name: Optional[str] = None) -> Any:
        """Get the information of each step

        Args:
            name: name of the pipeline or step. If None, get progress of all steps

        Returns:
            input and output of the respective pipeline or step
        """
        return self._context.get(name, context=self._progress)

    def steps(self):
        """Get the steps of the run

        Returns:
            the steps of the run
        """
        return self._context.get(context=self._progress).keys()

    def input(self, name: str = "") -> Any:
        """Get the input of a pipeline

        Args:
            name: name of the pipeline or step.

        Returns:
            input of the respective pipeline
        """
        return self.logs(name=name)["input"]

    def output(self, name: str = "") -> Any:
        """Get the output of a pipeline

        Args:
            name: name of the pipeline or step.

        Returns:
            output of the respective pipeline
        """
        return self.logs(name=name)["output"]

    def persist(self, store_result: str, run_id: str):
        """Persist the run result to a store

        Args:
            store_result: the store to persist the result
            run_id: the id of the run
        """
        path = Path(store_result) / run_id
        path.mkdir(parents=True, exist_ok=True)

        progress = self.logs(name=None)

        with (path / "progress.pkl").open("wb") as fo:
            pickle.dump(progress, fo)
        with (path / "input.pkl").open("wb") as fo:
            pickle.dump(progress["."]["input"], fo)
        with (path / "output.pkl").open("wb") as fo:
            pickle.dump(progress["."]["output"], fo)
        with (path / "config.yaml").open("w") as fo:
            yaml.safe_dump(self._config, fo)

    def id(self) -> str:
        """Get the id of the run

        Returns:
            the id of the run
        """
        return self._context.get("run_id", context=None)

    def load(self, run_path: str|Path):
        """Load a run

        Args:
            run_path: the path to the run
        """
        run_path = Path(run_path)
        with (run_path / "progress.pkl").open("rb") as fi:
            progress = pickle.load(fi)

        for key, value in progress.items():
            self.log_progress(key, **value)

    @property
    def config(self) -> Optional[dict]:
        """Get the config of the run

        Returns:
            the config of the run
        """
        return self._config

    @config.setter
    def config(self, config: dict):
        """Set the config of the run

        Args:
            config: the config of the run
        """
        self._config = config
