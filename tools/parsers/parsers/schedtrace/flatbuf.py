# SPDX-FileCopyrightText: Copyright (C) 2021-2026 Software Radio Systems Limited
# SPDX-License-Identifier: BSD-3-Clause-Open-MPI

"""Decoding of FlatBuffers buffers into plain values, given their schema (schema.py).

Tables become dicts of their fields; absent scalar fields take their default, or None when optional, and absent tables,
structs, vectors and unions are None. Structs become dicts, vectors lists, enums the names of their values (the number
for a value the schema does not know) and unions the dict of their member table, with its name as "type". Fields that
a newer writer appended to a table, beyond those of the schema, are ignored.
"""

from __future__ import annotations

import struct
from typing import Any

from .schema import SCALARS, Schema, Struct, Table, Type, scalar_of

_U16 = struct.Struct("<H")
_U32 = struct.Struct("<I")
_I32 = struct.Struct("<i")


class Decoder:
    """Decodes the buffers of a schema."""

    def __init__(self, schema: Schema):
        self.schema = schema
        self._scalars = {name: struct.Struct("<" + fmt) for name, (fmt, _) in SCALARS.items()}

    def root(self, buf: bytes | memoryview, offset: int = 0, root_type: str | None = None) -> dict[str, Any]:
        """The root table of the buffer that starts at offset of buf, of the root type of the schema by default."""
        name = root_type or self.schema.root_type
        if name is None:
            raise ValueError("No root type.")
        return self.table(buf, offset + _U32.unpack_from(buf, offset)[0], self.schema.tables[name])

    def table(self, buf: bytes | memoryview, pos: int, table: Table) -> dict[str, Any]:
        """The table of the given schema at pos of buf."""
        vtable = pos - _I32.unpack_from(buf, pos)[0]
        nof_slots = (_U16.unpack_from(buf, vtable)[0] - 4) // 2

        def slot_pos(slot: int) -> int:
            if slot >= nof_slots:
                return 0
            off = _U16.unpack_from(buf, vtable + 4 + 2 * slot)[0]
            return pos + off if off else 0

        out: dict[str, Any] = {}
        unions = self.schema.unions
        for f in table.fields:
            at = slot_pos(f.slot)
            name = f.type.name
            if name in unions:
                type_at = slot_pos(f.slot - 1)
                if f.type.vector:
                    out[f.name] = self._union_vector(buf, type_at, at, name)
                else:
                    kind = buf[type_at] if type_at else 0
                    out[f.name] = self._union(buf, kind, at, name) if at and kind else None
            elif f.type.vector:
                out[f.name] = self._vector(buf, at + _U32.unpack_from(buf, at)[0], f.type) if at else None
            elif (scalar := scalar_of(name, self.schema)) is not None:
                out[f.name] = self._scalar(buf, at, name, scalar) if at else self._default(f.default, name, scalar)
            elif name in self.schema.structs:
                out[f.name] = self._struct(buf, at, self.schema.structs[name]) if at else None
            elif name == "string":
                out[f.name] = self._string(buf, at + _U32.unpack_from(buf, at)[0]) if at else None
            else:
                out[f.name] = self.table(buf, at + _U32.unpack_from(buf, at)[0], self.schema.tables[name]) if at else None
        return out

    def _default(self, default: Any, type_name: str, scalar: str) -> Any:
        if default is None:
            return None
        if scalar == "bool":
            return bool(default)
        enum = self.schema.enums.get(type_name)
        return enum.names.get(default, default) if enum else default

    def _scalar(self, buf: bytes | memoryview, at: int, type_name: str, scalar: str) -> Any:
        value = self._scalars[scalar].unpack_from(buf, at)[0]
        enum = self.schema.enums.get(type_name)
        return enum.names.get(value, value) if enum else value

    def _struct(self, buf: bytes | memoryview, at: int, st: Struct) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for f, offset in zip(st.fields, st.offsets):
            scalar = scalar_of(f.type.name, self.schema)
            if scalar is not None:
                out[f.name] = self._scalar(buf, at + offset, f.type.name, scalar)
            else:
                out[f.name] = self._struct(buf, at + offset, self.schema.structs[f.type.name])
        return out

    def _string(self, buf: bytes | memoryview, at: int) -> str:
        length = _U32.unpack_from(buf, at)[0]
        return bytes(buf[at + 4 : at + 4 + length]).decode("utf-8", "replace")

    def _vector(self, buf: bytes | memoryview, at: int, vtype: Type) -> list[Any]:
        length = _U32.unpack_from(buf, at)[0]
        start = at + 4
        name = vtype.name
        if (scalar := scalar_of(name, self.schema)) is not None:
            size = SCALARS[scalar][1]
            return [self._scalar(buf, start + i * size, name, scalar) for i in range(length)]
        if name in self.schema.structs:
            st = self.schema.structs[name]
            return [self._struct(buf, start + i * st.size, st) for i in range(length)]
        if name == "string":
            return [self._string(buf, start + 4 * i + _U32.unpack_from(buf, start + 4 * i)[0]) for i in range(length)]
        table = self.schema.tables[name]
        return [self.table(buf, start + 4 * i + _U32.unpack_from(buf, start + 4 * i)[0], table) for i in range(length)]

    def _union(self, buf: bytes | memoryview, kind: int, at: int, union_name: str) -> dict[str, Any] | None:
        member = self.schema.unions[union_name].members.get(kind)
        if member is None:
            return {"type": kind}
        return {"type": member, **self.table(buf, at + _U32.unpack_from(buf, at)[0], self.schema.tables[member])}

    def _union_vector(self, buf: bytes | memoryview, types_at: int, values_at: int, union_name: str) -> list[Any] | None:
        if not types_at or not values_at:
            return None
        types_pos = types_at + _U32.unpack_from(buf, types_at)[0]
        values_pos = values_at + _U32.unpack_from(buf, values_at)[0]
        out = []
        for i in range(_U32.unpack_from(buf, types_pos)[0]):
            kind = buf[types_pos + 4 + i]
            elem = values_pos + 4 + 4 * i
            out.append(self._union(buf, kind, elem, union_name) if kind else None)
        return out
