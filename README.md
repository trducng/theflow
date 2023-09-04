<!-- # theflow -->

<p align="center">
  <img src="https://github-production-user-asset-6210df.s3.amazonaws.com/35283585/261831199-64e90674-e34e-42a5-bada-65cd21aae4ee.png">
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
pip install theflow
```

## Quick start

(A code walk-through of this session is stored in `examples/10-minutes-quick-start.ipynb`. You can run it with Google Colab (TODO - attach the link).)

Pipeline can be defined as code. You initialize all the ops in `self.initialize` and route them in `self.run`.

```python
from theflow import Compose

# Define some operations used inside the pipeline
# Operation 1: normal class-based Python object
class IncrementBy(Compose):

  x: int

  def run(self, y):
    return self.x + y

# Operation 2: normal Python function
def decrement_by_5(x):
  return x - 5

# Declare flow
class MathFlow(Compose):

  increment: Compose
  decrement: Compose

  def run(self, x):
    # Route the operations in the flow
    y = self.increment(x)
    y = self.decrement(y)
    y = self.increment(y)
    return y

flow = MathFlow(increment=IncrementBy(x=10), decrement=decrement_by_5)
```

You run the pipeline by directly calling it. The output is the same object returned by `self.run`.

```python
output = flow(x=5)
print(f"{output=}, {type(output)=}")      # output=5, type(output)=int
```

You can investigate pipeline's last run through the `last_run` property.

```python
flow.last_run.id()                        # id of the last run
flow.last_run.logs()                      # list all information of each step
# [TODO] flow.last_run.visualize(path="vis.png")   # export the graph in `vis.png` file
```

<!-- The information above is also automatically stored in the project root's `.theflow` directory. You can use the `flow` CLI command to list all runs, get each run detail, and compare runs. A UI for run management is trivially implemented with the `theflow[ui]` that allow managing the experiments through a web-based UI.

```shell
# list all runs in the directory
$ theflow list

# view detail of a run
$ theflow run <run-id>

# compare 2 runs
$ theflow diff <run-id-1> <run-id-2>

# show the UI, require `pip install theflow[ui]`, ctrl+c to stop the UI
$ theflow ui
```

(TODO - attach the UI screenshot).

`theflow` allows exporting the pipeline into a yaml file, which then can be used to share with each other

```python
flow.export_pipeline("pipeline.yaml")     # (TODO - attach screesamplesnshots)
```

You can modify the step inside the yaml file, and `theflow` can run the pipeline according to the new graph.

(TODO - attach URL to detailed documentation for each of the step above) -->

## Future features

- Arguments management
- Cache
  - cache by runs, organized by root task, allow reproducible
  - specify the files
  - the keys are like `lru_cache`, takes in the original input key, specify
    the cache, but the cache should be file-backed, for run-after-run execution.
  - cli command to manipulate cache
- Compare pipeline in a result folder
- Dynamically create reproducible config
- Support pipeline branching and merging
- Support single process or multi-processing pipeline running
- Can synchronize changes in the workflow, allowing logs from different run to be compatible with each other
- Compare different runs
  - Same cache directory
  - Compare evaluation result based on kwargs
- CLI List runs
- CLI Delete unnecessary runs
- Add coverage, pre-commit, CI...

## License

MIT License.
