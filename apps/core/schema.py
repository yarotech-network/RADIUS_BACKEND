import re


def annotate_api_errors_and_commands(result, generator, request, public):
    """Describe the shared wire envelope and only commands that implement keys."""
    result["components"]["schemas"]["ApiError"] = {
        "type": "object",
        "required": ["problem"],
        "additionalProperties": True,
        "properties": {"problem": {
            "type": "object",
            "required": ["code", "message", "fields"],
            "properties": {
                "code": {"type": "string"}, "message": {"type": "string"},
                "fields": {"type": "object", "additionalProperties": True},
            },
        }},
    }
    keyed = set()
    normalize = lambda path: re.sub(r"\{[^}]+\}", "{param}", path)
    for path, regex, method, callback in generator.endpoints:
        name = getattr(callback, "actions", {}).get(method.lower(), method.lower())
        handler = getattr(getattr(callback, "cls", None), name, None)
        if getattr(handler, "idempotency_supported", False):
            keyed.add((normalize(path), method.lower()))
    for path, item in result["paths"].items():
        for method, operation in item.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            codes = [400, 401, 403, 404]
            if method != "get":
                codes += [409, 503]
            for code in codes:
                operation["responses"].setdefault(str(code), {
                    "description": "API error; existing v1 fields are retained alongside problem.",
                    "content": {"application/json": {"schema": {"$ref": "#/components/schemas/ApiError"}}},
                })
            if (normalize(path), method) in keyed:
                operation.setdefault("parameters", []).append({
                    "in": "header", "name": "Idempotency-Key", "required": False,
                    "description": "Reuse for the same logical request. Changed payload or pending command returns 409. Do not automatically replace the key after a timeout.",
                    "schema": {"type": "string", "minLength": 16, "maxLength": 128, "pattern": "^[A-Za-z0-9_.:-]+$"},
                })
    return result
