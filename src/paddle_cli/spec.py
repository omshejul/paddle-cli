from __future__ import annotations

import copy
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

SPEC_URL = "https://raw.githubusercontent.com/PaddleHQ/paddle-openapi/main/v1/openapi.yaml"
HTTP_METHODS = ("get", "post", "patch", "put", "delete", "options", "head")


class SpecError(RuntimeError):
    """Raised when the Paddle API specification cannot be loaded."""


@dataclass(frozen=True)
class Parameter:
    name: str
    location: str
    required: bool
    description: str = ""
    schema: dict[str, Any] = field(default_factory=dict)
    example: Any = None


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    summary: str
    description: str
    tags: tuple[str, ...]
    parameters: tuple[Parameter, ...] = ()
    request_body: dict[str, Any] | None = None
    request_body_required: bool = False
    permission: str | None = None
    docs_url: str | None = None

    @property
    def is_write(self) -> bool:
        return self.method not in {"GET", "HEAD", "OPTIONS"}

    @property
    def label(self) -> str:
        return f"[{self.method}] {self.summary}  {self.path}"


def default_cache_path() -> Path:
    if cache_home := os.environ.get("XDG_CACHE_HOME"):
        root = Path(cache_home)
    elif os.name == "nt" and (local_app_data := os.environ.get("LOCALAPPDATA")):
        root = Path(local_app_data)
    elif os.sys.platform == "darwin":
        root = Path.home() / "Library" / "Caches"
    else:
        root = Path.home() / ".cache"
    return root / "paddle-cli" / "openapi-v1.yaml"


class SpecStore:
    def __init__(
        self,
        cache_path: Path | None = None,
        source_url: str = SPEC_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.cache_path = cache_path or default_cache_path()
        self.source_url = source_url
        self.transport = transport

    def update(self) -> Path:
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=30,
                follow_redirects=True,
            ) as client:
                response = client.get(self.source_url, headers={"Accept": "application/yaml"})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SpecError(f"Could not download Paddle's API specification: {exc}") from exc

        document = _parse_document(response.text)
        if not isinstance(document.get("paths"), dict):
            raise SpecError("Downloaded API specification does not contain a paths object.")

        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_suffix(".tmp")
        temporary_path.write_text(response.text, encoding="utf-8")
        temporary_path.replace(self.cache_path)
        return self.cache_path

    def load(self, *, refresh: bool = False) -> PaddleSpec:
        if refresh:
            self.update()
        elif not self.cache_path.exists():
            try:
                self.update()
            except SpecError:
                if not self.cache_path.exists():
                    raise

        try:
            text = self.cache_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise SpecError(f"Could not read cached API specification: {exc}") from exc
        return PaddleSpec(_parse_document(text))


def _parse_document(text: str) -> dict[str, Any]:
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SpecError(f"Paddle's API specification is not valid YAML: {exc}") from exc
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3."):
        raise SpecError("Downloaded document is not an OpenAPI 3 specification.")
    return document


class PaddleSpec:
    def __init__(self, document: dict[str, Any]) -> None:
        self.document = document
        self._tag_docs = {
            item["name"]: item.get("externalDocs", {}).get("url")
            for item in document.get("tags", [])
            if isinstance(item, dict) and item.get("name")
        }

    def resolve(self, value: Any) -> Any:
        if not isinstance(value, dict) or "$ref" not in value:
            return value
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise SpecError(f"Unsupported external OpenAPI reference: {reference}")
        target: Any = self.document
        for raw_part in reference[2:].split("/"):
            part = raw_part.replace("~1", "/").replace("~0", "~")
            try:
                target = target[part]
            except (KeyError, TypeError) as exc:
                raise SpecError(f"Broken OpenAPI reference: {reference}") from exc
        resolved = copy.deepcopy(target)
        siblings = {key: copy.deepcopy(item) for key, item in value.items() if key != "$ref"}
        if siblings and isinstance(resolved, dict):
            resolved.update(siblings)
        return resolved

    def operations(self) -> list[Operation]:
        operations: list[Operation] = []
        for path, raw_path_item in self.document.get("paths", {}).items():
            path_item = self.resolve(raw_path_item)
            if not isinstance(path_item, dict):
                continue
            shared_parameters = path_item.get("parameters", [])
            for method in HTTP_METHODS:
                raw_operation = path_item.get(method)
                if not isinstance(raw_operation, dict):
                    continue
                operation = self.resolve(raw_operation)
                parameters = self._parameters(
                    [*shared_parameters, *operation.get("parameters", [])]
                )
                body_schema, body_required = self._request_body(operation.get("requestBody"))
                tags = tuple(operation.get("tags") or ("Other",))
                description = operation.get("description", "") or ""
                operations.append(
                    Operation(
                        method=method.upper(),
                        path=path,
                        operation_id=operation.get("operationId", f"{method}-{path}"),
                        summary=operation.get("summary", operation.get("operationId", path)),
                        description=description,
                        tags=tags,
                        parameters=parameters,
                        request_body=body_schema,
                        request_body_required=body_required,
                        permission=_extract_permission(description),
                        docs_url=operation.get("externalDocs", {}).get("url")
                        or self._tag_docs.get(tags[0]),
                    )
                )
        return sorted(operations, key=lambda item: (item.tags[0].lower(), item.path, item.method))

    def _parameters(self, raw_parameters: list[Any]) -> tuple[Parameter, ...]:
        parameters: list[Parameter] = []
        seen: set[tuple[str, str]] = set()
        for raw_parameter in raw_parameters:
            value = self.resolve(raw_parameter)
            if not isinstance(value, dict) or not value.get("name") or not value.get("in"):
                continue
            key = (value["name"], value["in"])
            if key in seen:
                continue
            seen.add(key)
            schema = self.resolve(value.get("schema", {}))
            parameters.append(
                Parameter(
                    name=value["name"],
                    location=value["in"],
                    required=bool(value.get("required")) or value["in"] == "path",
                    description=value.get("description", "") or "",
                    schema=schema if isinstance(schema, dict) else {},
                    example=value.get(
                        "example", schema.get("example") if isinstance(schema, dict) else None
                    ),
                )
            )
        return tuple(parameters)

    def _request_body(self, raw_body: Any) -> tuple[dict[str, Any] | None, bool]:
        if not raw_body:
            return None, False
        body = self.resolve(raw_body)
        if not isinstance(body, dict):
            return None, False
        content = body.get("content", {})
        media = content.get("application/json")
        if not media and content:
            media = next(iter(content.values()))
        if not isinstance(media, dict):
            return None, bool(body.get("required"))
        schema = self.resolve(media.get("schema", {}))
        if isinstance(schema, dict):
            schema = copy.deepcopy(schema)
            if "example" not in schema and "example" in media:
                schema["example"] = media["example"]
        return schema if isinstance(schema, dict) else None, bool(body.get("required"))

    def example_for(self, schema: dict[str, Any] | None) -> Any:
        return self._example_for(schema or {}, seen=set(), depth=0)

    def _example_for(self, schema: dict[str, Any], *, seen: set[str], depth: int) -> Any:
        if depth > 8:
            return None
        if "$ref" in schema:
            reference = str(schema["$ref"])
            if reference in seen:
                return None
            return self._example_for(
                self.resolve(schema),
                seen={*seen, reference},
                depth=depth + 1,
            )
        if "example" in schema:
            return copy.deepcopy(schema["example"])
        if "default" in schema:
            return copy.deepcopy(schema["default"])
        for combinator in ("oneOf", "anyOf"):
            if schema.get(combinator):
                return self._example_for(schema[combinator][0], seen=seen, depth=depth + 1)
        if schema.get("allOf"):
            merged: dict[str, Any] = {}
            for part in schema["allOf"]:
                example = self._example_for(part, seen=seen, depth=depth + 1)
                if isinstance(example, dict):
                    merged.update(example)
            return merged
        if enum := schema.get("enum"):
            return enum[0]
        schema_type = schema.get("type")
        if schema_type == "object" or "properties" in schema:
            properties = schema.get("properties", {})
            required = set(schema.get("required", []))
            result: dict[str, Any] = {}
            for name, raw_property in properties.items():
                property_schema = self.resolve(raw_property)
                if name in required or "example" in property_schema or "default" in property_schema:
                    result[name] = self._example_for(
                        property_schema,
                        seen=seen,
                        depth=depth + 1,
                    )
            return result
        if schema_type == "array":
            return [self._example_for(schema.get("items", {}), seen=seen, depth=depth + 1)]
        if schema_type == "boolean":
            return False
        if schema_type in {"integer", "number"}:
            return schema.get("minimum", 0)
        if schema.get("format") == "date-time":
            return "2026-01-01T00:00:00Z"
        return ""


def _extract_permission(description: str) -> str | None:
    match = re.search(r"Requires\s+`([^`]+)`\s+permission", description, flags=re.IGNORECASE)
    return match.group(1) if match else None
