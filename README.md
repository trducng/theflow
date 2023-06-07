# finestflow


<p align="center">
  <img src="https://github-production-user-asset-6210df.s3.amazonaws.com/35283585/244143468-d3f886e7-5d4c-4d2d-899f-52e84fac7df5.png">
</p>

<p align="center">
    <em></em>
</p>

---

Most of the current workflow orchestrators focus on running the
already-developed pipelines in production. This library focuses on the pipeline
development process. It aims to make it easy to develop pipeline, and once the
user reaches a good pipeline, it aims to make it easy to export to other
production-grade workflow orchestrators.

- Allow both imperative and descriptive pipeline configuration
- Manage pipeline experiment: store pipeline output results, compare between
  different run results, reproduce experiments
- Cache progress, allow run from cache
- Can store artifacts locally for gitlfs/dvc/god/... tracking
- Initialize each task (avoid loading model)
- Support pipeline branching and merging
- Support single process or multi-processing pipeline running
- Support chaining different pipeline
- Visualize pipeline graph

## Quickstart

Install:

```shell
pip install finestflow
```

Imperative pipeline:


```python
from finestflow import Task, Pipeline


class Prompt(Task):

  class Meta:
    swapable = True

  prompt: xyz

  def __init__(self)
    super().__init__(*args, **kwargs)
    self.prompt.initialize(xyz)

  def run(self, *args, **kwargs):
    return self.prompt(**kwargs)

  def on_success(self)
    pass


class Run(Pipeline):
  prompt: Prompt
  pred: Pred
  parse: Parse

  class Meta:
    cache: xyz/
    name: "some pretty name"
    return_all: True

  def __call__(self, x):
    # GOOD: allow cache and code preparation
    y = self.prompt(x)
    y = self.pred(y)
    return self.parse(y)
    
Run(prompt={prompt: xyz}, pred=abc, parse=xmy)
```

- Questions:
  - How to allow init code? -> like the above
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
      the cache
    - cli command to manipulate cache
  - How to run multiple files in parallel? -> treat the parallel as a kind
    of pipeline
  - How to limit from - to steps -> monkey patching the task `__call__` func

## Tutorial

## TODO

- Allow step to plug-n-play the config
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
