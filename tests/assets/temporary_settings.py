from copy import deepcopy

from theflow.settings.default import CONTEXT, MIDDLEWARE

CONTEXT = deepcopy(CONTEXT)
CONTEXT["param"] = "value"

SETTING2 = "value2"
MIDDLEWARE["middleware-test"] = [
    "theflow.middleware.TrackProgressMiddleware",
    "theflow.middleware.CachingMiddleware",
]
