"""Plus One domain agents — Producer / Joiner / Controller.

These agents compose the framework primitives in :mod:`plus_one.core.agents.framework`
into a Plus One-specific reasoning loop:

  Producer  — generates Candidate places/regions from the user query
  Joiner    — fetches multi-source evidence per candidate and classifies
              each as local-gem / tourist-trap / neutral / insufficient
  Controller — decides whether to loop again (more candidates needed)
              or stop (enough coverage)

All three are plain ``async def`` callables; they conform to the
ProducerFn / JoinerFn / ControllerFn type aliases in the framework.
"""

from plus_one.agents.controller import ControllerInput, controller
from plus_one.agents.joiner import JoinedItem, joiner
from plus_one.agents.producer import Candidate, producer
from plus_one.agents.types import Classification, Evidence

__all__ = [
    "Candidate",
    "Classification",
    "ControllerInput",
    "Evidence",
    "JoinedItem",
    "controller",
    "joiner",
    "producer",
]
