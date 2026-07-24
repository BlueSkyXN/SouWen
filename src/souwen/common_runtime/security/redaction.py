"""Pure secret scrubbing for free-form text and URLs."""

from __future__ import annotations

import re
from urllib.parse import unquote_plus, urlsplit, urlunsplit


_SECRET_KEYWORDS = {
    "key",
    "keys",
    "secret",
    "token",
    "password",
    "sessdata",
    "authorization",
    "auth",
    "csrf",
    "cookie",
    "cookies",
    "jwt",
    "session",
    "sid",
    "xsrf",
}

_COMPACT_SECRET_FIELDS = {
    "accesskey",
    "accesskeys",
    "accesstoken",
    "apikey",
    "apikeys",
    "authtoken",
    "bearertoken",
    "clientsecret",
    "csrftoken",
    "credential",
    "credentials",
    "privatekey",
    "refreshtoken",
    "sessionid",
    "signingkey",
    "xapikey",
    "xcsrftoken",
    "xsessionid",
    "xxsrftoken",
    "xsrftoken",
}

_ACRONYM_BOUNDARY = re.compile(r"(.)([A-Z][a-z]+)")
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
_FIELD_SPLITTER = re.compile(r"[^A-Za-z0-9]+")
_URL_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s<>'\"]+", re.IGNORECASE)
_URL_USERINFO_RE = re.compile(r"\b([a-z][a-z0-9+.-]*://)([^/\s@]+)@", re.IGNORECASE)
_URL_TRAILING_PUNCTUATION = ".,;:!?"
_URL_TRAILING_BRACKETS = {
    ")": "(",
    "]": "[",
    "}": "{",
}
_SENSITIVE_KEY_RE = re.compile(
    r"(authorization|auth[_-]?token|api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|secret|password|passwd|pwd|x[_-]?api[_-]?key|"
    r"souwen[_-]?token|token|bearer|private[_-]?key|credential[s]?|"
    r"client[_-]?secret|signing[_-]?key|cookie|set[_-]?cookie|sessdata|"
    r"session[_-]?id|session|sid|jwt|csrf[_-]?token|xsrf[_-]?token|csrf|xsrf)",
    re.IGNORECASE,
)
_RE_BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9\-_.=+/]{6,})")
_RE_AUTH_HEADER_KV = re.compile(
    r"\b(?P<key>(?:proxy[-_])?authorization)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?:(?P<scheme>[A-Za-z][A-Za-z0-9_-]*)\s+)?"
    r"(?P<value>[^\s,;\"'}\]\*]+)",
    re.IGNORECASE,
)
_RE_QUOTED_KV = re.compile(
    r"(?P<key_quote>[\"'])"
    r"(?P<key>" + _SENSITIVE_KEY_RE.pattern + r")"
    r"(?P=key_quote)(?P<separator>\s*:\s*)"
    r"(?P<value_quote>[\"'])"
    r"(?P<value>.*?)"
    r"(?P=value_quote)",
    re.IGNORECASE,
)
_RE_QUOTED_SCALAR_KV = re.compile(
    r"(?P<key_quote>[\"'])"
    r"(?P<key>" + _SENSITIVE_KEY_RE.pattern + r")"
    r"(?P=key_quote)(?P<separator>\s*:\s*)"
    r"(?P<value>-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|none)"
    r"(?P<tail>\s*(?=[,}\]]|$))",
    re.IGNORECASE,
)
_RE_KV = re.compile(
    r"(?i)(" + _SENSITIVE_KEY_RE.pattern + r")\s*[:=]\s*[\"']?([^\s,\"'}\]\*]+)[\"']?"
)


def _is_secret_field(name: str) -> bool:
    """Return whether a field name usually carries secret material."""
    camel_split = _ACRONYM_BOUNDARY.sub(r"\1_\2", name)
    camel_split = _CAMEL_BOUNDARY.sub(r"\1_\2", camel_split)
    parts = [part.lower() for part in _FIELD_SPLITTER.split(camel_split) if part]
    if any(part in _SECRET_KEYWORDS for part in parts):
        return True
    compact = "".join(parts)
    return compact in _COMPACT_SECRET_FIELDS


def scrub_secret_text(text: str | None) -> str | None:
    """Redact Bearer tokens and common key-value secret assignments in plain text."""
    if not text or not isinstance(text, str):
        return text
    text = _RE_AUTH_HEADER_KV.sub(
        lambda match: f"{match.group('key')}{match.group('separator')}***",
        text,
    )
    text = _RE_BEARER.sub(lambda match: match.group(0).replace(match.group(1), "***"), text)
    text = _RE_QUOTED_KV.sub(
        lambda match: (
            f"{match.group('key_quote')}{match.group('key')}{match.group('key_quote')}"
            f"{match.group('separator')}{match.group('value_quote')}***{match.group('value_quote')}"
        ),
        text,
    )
    text = _RE_QUOTED_SCALAR_KV.sub(
        lambda match: (
            f"{match.group('key_quote')}{match.group('key')}{match.group('key_quote')}"
            f"{match.group('separator')}{match.group('key_quote')}***{match.group('key_quote')}"
            f"{match.group('tail')}"
        ),
        text,
    )
    return _RE_KV.sub(lambda match: f"{match.group(1)}:***", text)


def redact_secret_text(text: str | None) -> str | None:
    """Redact secrets embedded in free-form API response text."""
    if text is None:
        return None
    text = _URL_RE.sub(lambda match: _redact_text_url(match.group(0)), text)
    text = _URL_USERINFO_RE.sub(lambda match: f"{match.group(1)}***@", text)
    return scrub_secret_text(text)


def _redact_text_url(url: str) -> str:
    """Redact a URL embedded in prose while preserving trailing punctuation."""
    core = url
    suffix = ""
    while core and core[-1] in _URL_TRAILING_PUNCTUATION:
        suffix = core[-1] + suffix
        core = core[:-1]
    while core:
        opener = _URL_TRAILING_BRACKETS.get(core[-1])
        if not opener or core.count(core[-1]) <= core.count(opener):
            break
        suffix = core[-1] + suffix
        core = core[:-1]
    return f"{redact_secret_url(core)}{suffix}"


def _redact_url_params(params: str) -> str:
    """Redact query-style parameter values with sensitive field names."""
    parts: list[str] = []
    for item in re.split(r"([&;])", params):
        if item in {"&", ";"} or not item:
            parts.append(item)
            continue
        key, separator, _value = item.partition("=")
        if separator and _is_secret_field(unquote_plus(key)):
            parts.append(f"{key}{separator}***")
        else:
            parts.append(item)
    return "".join(parts)


def redact_secret_url(url: str | None) -> str:
    """Redact URL userinfo and sensitive parameter values for API display."""
    if not url:
        return ""

    parsed = urlsplit(url)
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = f"***@{netloc.rsplit('@', 1)[1]}"

    query = parsed.query
    if query:
        query = _redact_url_params(query)

    fragment = parsed.fragment
    if "=" in fragment:
        fragment = _redact_url_params(fragment)

    return urlunsplit((parsed.scheme, netloc, parsed.path, query, fragment))
