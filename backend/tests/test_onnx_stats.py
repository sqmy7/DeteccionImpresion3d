"""The ONNX parameter/GFLOPs counter, on a tiny model built by hand (protobuf bytes), so its numbers can be
checked on paper."""

from conftest import load_script

stats = load_script("onnx_stats")


def varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def field(number: int, payload: bytes | int) -> bytes:
    if isinstance(payload, int):
        return varint(number << 3) + varint(payload)
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def tensor(name: str, dims: list[int]) -> bytes:
    return b"".join(field(1, dim) for dim in dims) + field(8, name.encode())


def value_info(name: str, dims: list[int]) -> bytes:
    shape = b"".join(field(1, field(1, dim)) for dim in dims)  # Dimension{dim_value}
    tensor_type = field(2, shape)  # Tensor{shape}
    return field(1, name.encode()) + field(2, field(1, tensor_type))  # TypeProto{tensor_type}


def conv(inputs: list[str], output: str, groups: int = 1) -> bytes:
    attribute = field(1, b"group") + field(3, groups)
    return b"".join(field(1, i.encode()) for i in inputs) + field(2, output.encode()) + field(4, b"Conv") + field(5, attribute)


def test_parameters_and_gflops_of_a_two_layer_model(tmp_path):
    # Conv 3 -> 8, 3x3, output 1x8x32x32; then a depthwise (groups=8) 8 -> 8, 3x3, output 1x8x16x16.
    graph = b"".join(
        [
            field(1, conv(["x", "w1"], "y1")),
            field(1, conv(["y1", "w2"], "y2", groups=8)),
            field(5, tensor("w1", [8, 3, 3, 3])),  # 216
            field(5, tensor("w2", [8, 1, 3, 3])),  # 72
            field(5, tensor("b", [8])),  # 8
            field(12, value_info("y1", [1, 8, 32, 32])),
            field(12, value_info("y2", [1, 8, 16, 16])),
        ]
    )
    path = tmp_path / "tiny.onnx"
    path.write_bytes(field(7, graph))
    result = stats.analyze(path)
    assert result["parameters"] == 216 + 72 + 8
    macs = 8 * 3 * 3 * 3 * 32 * 32 + 8 * 1 * 3 * 3 * 16 * 16
    assert result["gflops"] == round(2 * macs / 1e9, 2) or abs(result["gflops"] - 2 * macs / 1e9) < 0.005
    assert result["conv_matmul_counted"] == 2 and result["conv_matmul_without_shape"] == 0


def test_without_declared_shapes_gflops_are_not_made_up(tmp_path):
    graph = field(1, conv(["x", "w1"], "y1")) + field(5, tensor("w1", [8, 3, 3, 3]))
    path = tmp_path / "noshape.onnx"
    path.write_bytes(field(7, graph))
    result = stats.analyze(path)
    assert result["parameters"] == 216 and result["gflops"] is None and result["conv_matmul_without_shape"] == 1
