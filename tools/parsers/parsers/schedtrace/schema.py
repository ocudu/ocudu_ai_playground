# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""FlatBuffers schemas (.fbs), as the decoder of flatbuf.py needs them: the enums, structs, tables and unions of a
schema file and the ones it includes.

Covers the subset of the FlatBuffers schema language that the schedtrace schemas use: include, namespace, enum,
struct, table, union, root_type and attribute declarations, scalar, struct, table, union and vector types, and field
defaults, "null" for optional scalars. Field attributes in parentheses are skipped, except explicit field ids, which
are rejected, as is other syntax outside the subset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# struct format and size of each scalar type, by its names in the schema language.
SCALARS: dict[str, tuple[str, int]] = {
    "bool": ("?", 1),
    "byte": ("b", 1), "int8": ("b", 1),
    "ubyte": ("B", 1), "uint8": ("B", 1),
    "short": ("h", 2), "int16": ("h", 2),
    "ushort": ("H", 2), "uint16": ("H", 2),
    "int": ("i", 4), "int32": ("i", 4),
    "uint": ("I", 4), "uint32": ("I", 4),
    "long": ("q", 8), "int64": ("q", 8),
    "ulong": ("Q", 8), "uint64": ("Q", 8),
    "float": ("f", 4), "float32": ("f", 4),
    "double": ("d", 8), "float64": ("d", 8),
}

_TOKEN_RE = re.compile(
    r'\s+|//[^\n]*|/\*.*?\*/|"[^"]*"|[A-Za-z_][\w.]*|-?0[xX][0-9a-fA-F]+|-?[\d.]+(?:[eE][+-]?\d+)?|.', re.DOTALL
)


@dataclass
class Type:
    """Type of a field: a scalar, "string", or the name of an enum, struct, table or union, possibly in a vector."""

    name: str
    vector: bool = False


@dataclass
class Field:
    name: str
    type: Type
    # Default of a scalar field, None for "= null", i.e. optional, which is then absent rather than its default.
    default: int | float | bool | str | None = 0
    # Slot of the field in the vtable of its table. A union field takes two: its type is in the slot before.
    slot: int = 0


@dataclass
class Enum:
    name: str
    base: str
    names: dict[int, str] = field(default_factory=dict)


@dataclass
class Struct:
    name: str
    fields: list[Field] = field(default_factory=list)
    # Offset of each field, size and alignment, as FlatBuffers lays a struct out.
    offsets: list[int] = field(default_factory=list)
    size: int = 0
    align: int = 1


@dataclass
class Table:
    name: str
    fields: list[Field] = field(default_factory=list)


@dataclass
class Union:
    name: str
    # Member tables by union type, which starts at 1: 0 is NONE.
    members: dict[int, str] = field(default_factory=dict)


@dataclass
class Schema:
    enums: dict[str, Enum] = field(default_factory=dict)
    structs: dict[str, Struct] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    unions: dict[str, Union] = field(default_factory=dict)
    root_type: str | None = None


def load(path: str | Path) -> Schema:
    """The schema of a .fbs file and of the files it includes, which are looked up next to it."""
    schema = Schema()
    _load_file(Path(path), schema, set())
    for struct in schema.structs.values():
        _layout(struct, schema)
    for table in [*schema.tables.values(), *schema.structs.values()]:
        for f in table.fields:
            if isinstance(f.default, str):
                f.default = _enum_value(f, schema)
    return schema


def _enum_value(f: Field, schema: Schema) -> int:
    """The value of the enum default of a field, given by name."""
    enum = schema.enums.get(f.type.name)
    values = {name: value for value, name in enum.names.items()} if enum else {}
    if f.default not in values:
        raise ValueError(f"field {f.name}: default {f.default!r} is not a value of {f.type.name}")
    return values[f.default]


def _load_file(path: Path, schema: Schema, seen: set[Path]) -> None:
    path = path.resolve()
    if path in seen:
        return
    seen.add(path)
    tokens = [t for t in _TOKEN_RE.findall(path.read_text()) if t.strip() and not t.startswith(("//", "/*"))]
    pos = 0

    def take(expected: str | None = None) -> str:
        nonlocal pos
        token = tokens[pos]
        if expected is not None and token != expected:
            raise ValueError(f"{path.name}: expected {expected!r}, got {token!r}")
        pos += 1
        return token

    while pos < len(tokens):
        keyword = take()
        if keyword == "include":
            _load_file(path.parent / take().strip('"'), schema, seen)
            take(";")
        elif keyword in ("namespace", "attribute", "file_identifier", "file_extension"):
            while take() != ";":
                pass
        elif keyword == "root_type":
            schema.root_type = _short(take())
            take(";")
        elif keyword == "enum":
            enum = Enum(take(), "")
            take(":")
            enum.base = take()
            take("{")
            value = 0
            while (name := take()) != "}":
                if name == ",":
                    continue
                if tokens[pos] == "=":
                    take("=")
                    value = int(take(), 0)
                if tokens[pos] not in (",", "}"):
                    raise ValueError(f"{path.name}: unsupported syntax {tokens[pos]!r} in enum {enum.name}")
                enum.names[value] = name
                value += 1
            schema.enums[enum.name] = enum
        elif keyword == "union":
            union = Union(take())
            take("{")
            index = 1
            while (name := take()) != "}":
                if name == ",":
                    continue
                if tokens[pos] == "=":
                    take("=")
                    index = int(take(), 0)
                if tokens[pos] not in (",", "}"):
                    raise ValueError(f"{path.name}: unsupported syntax {tokens[pos]!r} in union {union.name}")
                union.members[index] = _short(name)
                index += 1
            schema.unions[union.name] = union
        elif keyword in ("table", "struct"):
            name = take()
            fields: list[Field] = []
            take("{")
            while tokens[pos] != "}":
                field_name = take()
                take(":")
                if tokens[pos] == "[":
                    take("[")
                    ftype = Type(_short(take()), vector=True)
                    take("]")
                else:
                    ftype = Type(_short(take()))
                default: int | float | bool | str | None = 0
                if tokens[pos] == "=":
                    take("=")
                    default = _value(take())
                if tokens[pos] == "(":
                    while (attribute := take()) != ")":
                        # Explicit ids reorder the slots, which fields take in declaration order here.
                        if attribute == "id":
                            raise ValueError(f"{path.name}: unsupported attribute id of field {name}.{field_name}")
                take(";")
                fields.append(Field(field_name, ftype, default))
            take("}")
            if keyword == "struct":
                schema.structs[name] = Struct(name, fields)
            else:
                schema.tables[name] = Table(name, fields)
        else:
            raise ValueError(f"{path.name}: unsupported declaration {keyword!r}")
    # Slots are assigned once all unions are known, since union fields take two.
    for table in schema.tables.values():
        slot = 0
        for f in table.fields:
            f.slot = slot + (1 if f.type.name in schema.unions else 0)
            slot = f.slot + 1


def _short(name: str) -> str:
    """A type name without its namespace."""
    return name.rsplit(".", 1)[-1]


def _value(token: str) -> int | float | bool | str | None:
    """The default of a field: a number, a bool, None for null, or the name of an enum value."""
    if token == "null":
        return None
    if token in ("true", "false"):
        return token == "true"
    if token[:1].isalpha() or token[:1] == "_":
        return token
    if token.lstrip("-")[:2].lower() == "0x":
        return int(token, 16)
    return float(token) if any(c in token for c in ".eE") else int(token, 0)


def scalar_of(type_name: str, schema: Schema) -> str | None:
    """The scalar type of a type: itself for a scalar, the base of an enum, else None."""
    if type_name in SCALARS:
        return type_name
    if type_name in schema.enums:
        return schema.enums[type_name].base
    return None


def _layout(struct: Struct, schema: Schema) -> None:
    """Lays a struct out as FlatBuffers does: each field at the next offset aligned to its own alignment, and the
    struct padded to a multiple of its largest field alignment.
    """
    if struct.offsets:
        return
    offset, align = 0, 1
    for f in struct.fields:
        if (scalar := scalar_of(f.type.name, schema)) is not None:
            size = falign = SCALARS[scalar][1]
        else:
            inner = schema.structs[f.type.name]
            _layout(inner, schema)
            size, falign = inner.size, inner.align
        offset = (offset + falign - 1) // falign * falign
        struct.offsets.append(offset)
        offset += size
        align = max(align, falign)
    struct.size = (offset + align - 1) // align * align
    struct.align = align
