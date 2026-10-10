"""Parameter count and estimated GFLOPs of an ONNX model, reading the file's protobuf directly (no onnx
or onnxruntime needed). Only reads the file.

  - Parameters: the number of elements of every initializer (weights, biases and the few constants
    the exporter folded in; a Conv followed by BatchNorm was fused at export, so this is the deployed
    model's count, not the training one's).
  - GFLOPs: 2 x multiply-accumulates of every Conv and MatMul/Gemm, from the weights' shapes and the
    output shapes the file declares (value_info). Elementwise ops, resizes and the NMS-free head's
    post-processing are not counted. Reported as an estimate; it is None when the file declares no shapes.

usage:  backend\\.venv\\Scripts\\python.exe backend\\scripts\\onnx_stats.py inference\\models\\best_fp32.onnx
"""

import json
import math
import sys
from pathlib import Path


def read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def fields(data: bytes):
    """(field number, wire type, value) for each field of a protobuf message; length-delimited
    values are bytes, varints are ints, fixed-size values are bytes."""
    pos = 0
    while pos < len(data):
        key, pos = read_varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = read_varint(data, pos)
        elif wire == 2:
            length, pos = read_varint(data, pos)
            value, pos = data[pos : pos + length], pos + length
        elif wire == 1:
            value, pos = data[pos : pos + 8], pos + 8
        elif wire == 5:
            value, pos = data[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"wire type {wire} not supported")
        yield number, wire, value


def packed_varints(blob: bytes) -> list[int]:
    out, pos = [], 0
    while pos < len(blob):
        value, pos = read_varint(blob, pos)
        out.append(value)
    return out


def tensor_dims(tensor: bytes) -> tuple[str, list[int]]:
    name, dims = "", []
    for number, wire, value in fields(tensor):
        if number == 1:
            dims += packed_varints(value) if wire == 2 else [value]
        elif number == 8:
            name = value.decode("utf-8", "replace")
    return name, dims


def value_info_shape(info: bytes) -> tuple[str, list[int] | None]:
    name, shape = "", None
    for number, _, value in fields(info):
        if number == 1:
            name = value.decode("utf-8", "replace")
        elif number == 2:  # TypeProto
            for t_number, _, t_value in fields(value):
                if t_number == 1:  # tensor_type
                    for tt_number, _, tt_value in fields(t_value):
                        if tt_number == 2:  # shape
                            shape = []
                            for s_number, _, s_value in fields(tt_value):
                                if s_number == 1:  # dim
                                    dim = next((v for n, w, v in fields(s_value) if n == 1 and w == 0), None)
                                    shape.append(dim if dim is not None else 0)
    return name, shape


def node_info(node: bytes) -> dict:
    info = {"inputs": [], "outputs": [], "op": "", "groups": 1}
    for number, wire, value in fields(node):
        if number == 1:
            info["inputs"].append(value.decode("utf-8", "replace"))
        elif number == 2:
            info["outputs"].append(value.decode("utf-8", "replace"))
        elif number == 4:
            info["op"] = value.decode("utf-8", "replace")
        elif number == 5:  # attribute
            name, ivalue = "", None
            for a_number, a_wire, a_value in fields(value):
                if a_number == 1:
                    name = a_value.decode("utf-8", "replace")
                elif a_number == 3 and a_wire == 0:
                    ivalue = a_value
            if name == "group" and ivalue:
                info["groups"] = ivalue
    return info


def analyze(path: Path) -> dict:
    graph = next(value for number, _, value in fields(path.read_bytes()) if number == 7)
    weights: dict[str, list[int]] = {}
    shapes: dict[str, list[int]] = {}
    nodes: list[dict] = []
    for number, _, value in fields(graph):
        if number == 5:
            name, dims = tensor_dims(value)
            weights[name] = dims
        elif number in (11, 12, 13):  # input, output, value_info
            name, shape = value_info_shape(value)
            if shape:
                shapes[name] = shape
        elif number == 1:
            nodes.append(node_info(value))

    parameters = sum(math.prod(dims) if dims else 1 for dims in weights.values())
    macs, counted, missing = 0, 0, 0
    for node in nodes:
        if node["op"] == "Conv" and len(node["inputs"]) > 1 and node["inputs"][1] in weights:
            out_shape = shapes.get(node["outputs"][0])
            kernel = weights[node["inputs"][1]]  # [Cout, Cin/groups, kh, kw]
            if out_shape and len(out_shape) == 4 and len(kernel) == 4 and all(out_shape[2:]):
                macs += kernel[0] * kernel[1] * kernel[2] * kernel[3] * out_shape[2] * out_shape[3]
                counted += 1
            else:
                missing += 1
        elif node["op"] in ("MatMul", "Gemm") and len(node["inputs"]) > 1:
            out_shape = shapes.get(node["outputs"][0])
            weight = weights.get(node["inputs"][1])
            if out_shape and weight and len(weight) == 2:
                macs += math.prod(d for d in out_shape[:-1] if d) * weight[0] * weight[1]
                counted += 1
            else:
                missing += 1
    return {
        "file": path.name,
        "size_mb": round(path.stat().st_size / 1e6, 2),
        "nodes": len(nodes),
        "initializers": len(weights),
        "parameters": parameters,
        "gflops": round(2 * macs / 1e9, 2) if counted and not missing else None,
        "gflops_partial": round(2 * macs / 1e9, 2) if counted and missing else None,
        "conv_matmul_counted": counted,
        "conv_matmul_without_shape": missing,
        "declared_shapes": len(shapes),
    }


if __name__ == "__main__":
    print(json.dumps([analyze(Path(arg)) for arg in sys.argv[1:]], indent=2))
