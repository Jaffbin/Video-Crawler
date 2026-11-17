"""Auto-organize rules: when a download is saved, tag it, add it to collections or mark it as a favorite.

Rules only change virtual classification (tags, collections, favorite); they never move, rename or
delete files. Every condition in a rule must match, and every enabled matching rule applies.
"""
from __future__ import annotations

import re
import uuid

RULE_LIMIT = 50
TAG_LIMIT = 20          # matches MediaLibrary.describe
RULE_TAG_LIMIT = 10
RULE_COLLECTION_LIMIT = 20
KINDS = ("video", "audio", "image")
DOMAIN_RE = re.compile(r"^(?=.{1,200}$)[a-z0-9-]+(\.[a-z0-9-]+)+$")
FORMAT_RE = re.compile(r"^\.[a-z0-9]{1,10}$")
CONTROL_RE = re.compile(r"[\x00-\x1f]")
ID_RE = re.compile(r"^[0-9a-f]{32}$")


def normalize_source(value) -> str:
    """Accept "bilibili.com", "www.bilibili.com" or a pasted link; store just the site name."""
    if not isinstance(value, str):
        raise ValueError("Enter a site such as bilibili.com.")
    text = value.strip().lower()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text).split("/", 1)[0].split(":", 1)[0]
    text = text.removeprefix("*.").removeprefix("www.")
    if not DOMAIN_RE.match(text):
        raise ValueError("Enter a site such as bilibili.com.")
    return text


def check_rule(value, collection_ids) -> dict:
    """Validate one rule. Raises ValueError with a message the UI can show."""
    if not isinstance(value, dict):
        raise ValueError("Invalid auto rule.")
    name = value.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or CONTROL_RE.search(name):
        raise ValueError("Use a rule name of 1–80 characters.")
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("Invalid auto rule.")

    raw_conditions = value.get("conditions")
    if not isinstance(raw_conditions, dict) or set(raw_conditions) - {"source", "kind", "format"}:
        raise ValueError("Choose a site, a file type or a format.")
    conditions = {}
    if raw_conditions.get("source") not in (None, ""):
        conditions["source"] = normalize_source(raw_conditions["source"])
    if raw_conditions.get("kind") not in (None, ""):
        if raw_conditions["kind"] not in KINDS:
            raise ValueError("Choose video, audio or image.")
        conditions["kind"] = raw_conditions["kind"]
    if raw_conditions.get("format") not in (None, ""):
        fmt = raw_conditions["format"]
        fmt = ("." + fmt.strip().lower().lstrip(".")) if isinstance(fmt, str) else ""
        if not FORMAT_RE.match(fmt):
            raise ValueError("Enter a format such as .mp3.")
        conditions["format"] = fmt
    if not conditions:
        raise ValueError("Choose a site, a file type or a format.")

    raw_actions = value.get("actions")
    if not isinstance(raw_actions, dict) or set(raw_actions) - {"tags", "collections", "favorite", "export"}:
        raise ValueError("Choose tags, collections or favorite.")
    actions = {}
    tags = raw_actions.get("tags", [])
    if (not isinstance(tags, list) or len(tags) > RULE_TAG_LIMIT
            or any(not isinstance(tag, str) or not 1 <= len(tag.strip()) <= 40 or CONTROL_RE.search(tag)
                   for tag in tags)):
        raise ValueError(f"Use up to {RULE_TAG_LIMIT} tags of 40 characters.")
    unique_tags = {}
    for tag in tags:
        unique_tags.setdefault(tag.strip().casefold(), tag.strip())
    if unique_tags:
        actions["tags"] = list(unique_tags.values())
    collections = raw_actions.get("collections", [])
    if (not isinstance(collections, list) or len(collections) > RULE_COLLECTION_LIMIT
            or any(not isinstance(item, str) or not ID_RE.match(item) for item in collections)):
        raise ValueError("Choose collections from the list.")
    if any(item not in collection_ids for item in collections):
        raise ValueError("A chosen collection no longer exists. Refresh Library.")
    if collections:
        actions["collections"] = list(dict.fromkeys(collections))
    favorite = raw_actions.get("favorite", False)
    if not isinstance(favorite, bool):
        raise ValueError("Invalid auto rule.")
    if favorite:
        actions["favorite"] = True
    export = raw_actions.get("export", False)
    if not isinstance(export, bool):
        raise ValueError("Invalid auto rule.")
    if export:
        actions["export"] = True  # place matching videos in the media server folder
    if not actions:
        raise ValueError("Choose tags, collections or favorite.")
    return {"name": name.strip(), "enabled": enabled, "conditions": conditions, "actions": actions}


def rule_records(value, collection_ids) -> dict:
    """Saved rules, dropping any that no longer validate (for example a hand-edited file)."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in list(value.items())[:RULE_LIMIT]:
        if not isinstance(key, str) or not ID_RE.match(key):
            continue
        if isinstance(item, dict) and isinstance(item.get("actions"), dict):
            # A deleted collection should not disable the whole rule.
            item = {**item, "actions": {**item["actions"], "collections": [
                c for c in item["actions"].get("collections", []) if c in collection_ids]}}
            if not item["actions"]["collections"]:
                del item["actions"]["collections"]
        try:
            result[key] = check_rule(item, collection_ids)
        except ValueError:
            continue
    return result


def change(rules: dict, action, rule_id, value, collection_ids) -> str:
    """Create, update or delete a rule in ``rules`` (modified in place). Returns the rule id."""
    if action not in ("create", "update", "delete"):
        raise ValueError("Choose a valid auto rule action.")
    if action != "create" and (not isinstance(rule_id, str) or rule_id not in rules):
        raise ValueError("Auto rule no longer exists. Refresh Library.")
    if action == "delete":
        del rules[rule_id]
        return rule_id
    record = check_rule(value, collection_ids)
    if any(item["name"].casefold() == record["name"].casefold() and key != rule_id for key, item in rules.items()):
        raise ValueError("An auto rule with that name already exists.")
    if action == "create":
        if len(rules) >= RULE_LIMIT:
            raise ValueError(f"Use up to {RULE_LIMIT} auto rules.")
        rule_id = uuid.uuid4().hex
    rules[rule_id] = record
    return rule_id


def matches(rule: dict, relative: str, record: dict, kind: str) -> bool:
    if not rule["enabled"]:
        return False
    conditions = rule["conditions"]
    if "source" in conditions:
        # The Library stores the URL's host as written, which can include a port.
        host = str(record.get("source") or "").lower().rsplit("@", 1)[-1].split(":", 1)[0]
        if host != conditions["source"] and not host.endswith("." + conditions["source"]):
            return False
    if "kind" in conditions and kind != conditions["kind"]:
        return False
    if "format" in conditions and not relative.lower().endswith(conditions["format"]):
        return False
    return True


def apply(rule: dict, record: dict, collection_ids) -> None:
    """Add this rule's classification to ``record`` without removing anything already there."""
    actions = rule["actions"]
    if actions.get("tags"):
        existing = [tag for tag in record.get("tags", []) if isinstance(tag, str)] \
            if isinstance(record.get("tags"), list) else []
        unique = {}
        for tag in [*existing, *actions["tags"]]:
            unique.setdefault(tag.casefold(), tag)
        record["tags"] = list(unique.values())[:TAG_LIMIT]
    if actions.get("collections"):
        ids = record.get("collections", [])
        ids = [key for key in ids if isinstance(key, str) and key in collection_ids] if isinstance(ids, list) else []
        record["collections"] = list(dict.fromkeys([*ids, *(c for c in actions["collections"] if c in collection_ids)]))
    if actions.get("favorite"):
        record["favorite"] = True
