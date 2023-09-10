from copy import deepcopy

from theflow.settings.default import CONTEXT

CONTEXT = deepcopy(CONTEXT)
CONTEXT["param"] = "value"

SETTING2 = "value2"
