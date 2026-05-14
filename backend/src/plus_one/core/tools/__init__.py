"""Tools — typed external operations the agent framework can call.

Each tool conforms to ``plus_one.core.agents.framework.Tool`` (Protocol):
``name``, ``input_schema``, ``is_concurrency_safe``, and ``async execute()``.

Tools in this batch (2c) are **fixture-backed only**. Live implementations
(real Reddit API, real XHS scraping, real Google Places) come in a later
batch. The fixture layer is what the agents call against during demos and
unit tests; live mode will be a swap-in subclass with no agent-side change.
"""

from plus_one.core.tools.google_places import (
    GooglePlacesSearchInput,
    GooglePlacesSearchTool,
    Place,
)
from plus_one.core.tools.reddit import RedditPost, RedditSearchInput, RedditSearchTool
from plus_one.core.tools.xiaohongshu import (
    XHSPost,
    XHSSearchInput,
    XHSSearchTool,
)

__all__ = [
    "GooglePlacesSearchInput",
    "GooglePlacesSearchTool",
    "Place",
    "RedditPost",
    "RedditSearchInput",
    "RedditSearchTool",
    "XHSPost",
    "XHSSearchInput",
    "XHSSearchTool",
]
