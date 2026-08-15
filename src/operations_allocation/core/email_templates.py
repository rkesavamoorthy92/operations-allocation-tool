"""Email template rendering — restricted token substitution, no eval().

Implements PROJECT_SPEC.md section 18's supported placeholders exactly:
``{{associate_name}}``, ``{{program_name}}``, ``{{run_id}}``,
``{{item_count}}``, ``{{due_date}}``. Like core.qc, there is no
expression-execution path here -- ``render_template()`` only ever does
literal substring replacement of a closed set of recognized tokens.

An unsupported placeholder in a template (e.g. a typo, or something an
untrusted config author tried to sneak in) is a configuration error and
is rejected loudly rather than left in the output or silently dropped.
"""

from __future__ import annotations

import re
from typing import Mapping

from operations_allocation.domain.exceptions import EmailTemplateError

SUPPORTED_TOKENS = frozenset({"associate_name", "program_name", "run_id", "item_count", "due_date"})
_TOKEN_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_]+)\s*\}\}")


def render_template(template: str, values: Mapping[str, str]) -> str:
    """Substitute ``{{token}}`` placeholders in ``template`` using ``values``.

    Raises :class:`EmailTemplateError` if the template references a token
    outside :data:`SUPPORTED_TOKENS`, or references a supported token this
    draft type does not have a value for (e.g. ``{{associate_name}}`` in a
    consolidated team email).
    """
    def _substitute(match: re.Match[str]) -> str:
        token = match.group(1)
        if token not in SUPPORTED_TOKENS:
            raise EmailTemplateError(f"Unsupported email template placeholder '{{{{{token}}}}}'. Supported placeholders: {sorted(SUPPORTED_TOKENS)}.")
        if token not in values:
            raise EmailTemplateError(f"Email template uses '{{{{{token}}}}}', which has no value for this draft type.")
        return values[token]

    return _TOKEN_PATTERN.sub(_substitute, template)
