<!-- # finestflow -->

<p align="center">
  <img src="https://github-production-user-asset-6210df.s3.amazonaws.com/35283585/244143468-d3f886e7-5d4c-4d2d-899f-52e84fac7df5.png">
</p>

<p align="center">
    <em>Pipeline development framework, easy to experiment and compare different pipelines, quick to deploy to workflow orchestration tools</em>
</p>

---

Most of the current workflow orchestrators focus on executing the already-developed pipelines in production. This library focuses on the **pipeline development process**. It aims to make it easy to develop pipeline, and once the user reaches a good pipeline, it aims to make it easy to export to other production-grade workflow orchestrators. Notable features:

- Manage pipeline experiment: store pipeline run outputs, compare pipelines & visualize.
- Support pipeline as code: allow complex customization.
- Support pipeline as configuration - suitable for plug-and-play when pipeline is more stable.
- Fast pipeline execution, auto-cache & run from cache when necessary.
- Allow version control of artifacts with git-lfs/dvc/god...
- Export pipeline to compatible workflow orchestration tools (e.g. Argo workflow, Airflow, Kubeflow...).

## Install

```shell
pip install finestflow
```

## Quick start

(A code walk-through of this session is stored in `examples/10-minutes-quick-start.ipynb`. You can run it with Google Colab (TODO - attach the link).)

Pipeline can be defined as code. You initialize all the ops in `self.initialize` and route them in `self.run`. In `self.run`, you associate each step with a name `_ff_name`, which finestflow use to identify the edge in the flow graph.

```python
from finestflow import Pipeline

# Operation 1: normal class-based Python object
class IncrementBy:

  def __init__(self, x):
    self.x = x

  def __call__(self, y):
    import time.time
    time.sleep(10)
    return self.x + y

# Operation 2: normal Python function
def decrement_by_5(x):
  return x - 5

# Declare flow
class MathFlow(Pipeline):

  def initialize(self):
    # register operations in the flow
    self.increment = IncrementBy(x=self._ff_kwargs["increment"])
    self.decrement = decrement_by_5

  def run(self, x):
    # routing of the flow
    y = self.increment(x, _ff_name="increment1")   # associate _ff_name
    y = self.decrement(y, _ff_name="decrement")
    y = self.increment(x, _ff_name="increment2")
    return y

flow = MathFlow(kwargs={"increment": 10})
```

You run the pipeline by directly calling it. The output is the same object returned by `self.run`.

```python
output = flow.run(x=5)
print(f"{output=}, {type(output)=}")      # output=5, type(output)=int
```

You can investigate pipeline's last run through the `last_run` property.

```python
flow.last_run.id()                        # id of the last run
flow.last_run.visualize(path="vis.png")   # export the graph in `vis.png` file
flow.last_run.steps()                     # list input/output each step
```

The information above is also automatically stored in the project root `.finestflow` directory. You can use the finestflow CLI command to list all runs, get each run detail, and compare runs. A UI for run management is trivially implemented with the `finestflow[ui]` that allow managing the experiments through a web-based UI.

```shell
# list all runs in the directory
$ finestflow list

# view detail of a run
$ finestflow run <run-id>

# compare 2 runs
$ finestflow diff <run-id-1> <run-id-2>

# show the UI, require `pip install finestflow[ui]`, ctrl+c to stop the UI
$ finestflow ui
```

(TODO - attach the UI screenshot).

`finestflow` allows exporting the pipeline into a yaml file, which then can be used to share with each other

```python
flow.export_pipeline("pipeline.yaml")     # (TODO - attach screesamplesnshots)
```

You can modify the step inside the yaml file, and `finestflow` can run the pipeline according to the new graph.

(TODO - attach URL to detailed documentation for each of the step above)

## Roadmap

- Questions:
  - How to allow plug-and-play object? (e.g. different Prompt object?), well
    just supplies the class object
  - How to make it configurable -> Allow to export pipeline to config (magic
    with the task and flow's `__init__` -> Allow to load from config -> For
    pipeline that doesn't have class, then the pipeline's `__call__` can be
    inferred or explicitly draw in the kind of airflow notation
  - How to store the cache?
    - cache by runs, organized by root task, allow reproducible
    - specify the files
    - the keys are like `lru_cache`, takes in the original input key, specify
      the cache, but the cache should be file-backed, for run-after-run execution.
    - cli command to manipulate cache
  - How to run multiple files in parallel? -> treat the parallel as a kind
    of pipeline
  - How to limit from - to steps -> monkey patching the task `__call__` func
- Compare pipeline in a result folder
- Cache progress, allow running from cache
- Allow step to plug-n-play the config
- Initialize each task (avoid loading model)
- Support pipeline branching and merging
- Support single process or multi-processing pipeline running
- Support chaining different pipeline
- Allow debugging
- Can synchronize changes in the workflow, allowing logs from different run to be compatible with each other
- Compare different runs
  - Same cache directory
  - Compare evaluation result based on kwargs
- List runs
- Delete unnecessary runs
- Dynamically create reproducible config
- Prepare README and create open-source
- Recursive construction of flow:
  - Config are parsed recursively.
- How to secure environment variables in each step, in such a way that it's not possible for one step to access to environment of other step
  - This is a deployment problem, not development problem.
    - It should be handled in the Yaml config. Not in the code.
    - Integrate the deployment with argo-workflow
- [-] Allow step to have the name of the edge
  - [ ] Edge name check
- [-] Allow step to have read/write access to the same memory space so that it can help with tracing
  - [ ] Design better context interface
  - [ ] Should have a context manager to separate parallel run
- [-] Allow step to store output in a cache
  - [ ] Optimize the amount of information stored
- [-] Allow step to start and end at will
- [-] Persist the log to disk
- [-] Perform repeated experiments -> Use prefix for pipeline
