# tdjson-rs

`tdjson-rs` provides fast, native Python bindings for the JSON interface of [TDLib](https://github.com/tdlib/td).

The backend is [td-rs](https://github.com/td-rs/td) — the Rust implementation of TDLib — compiled **directly into the extension module**. There is no `libtdjson.so` to ship, load, or version-match: `import tdjson` is self-contained.

## How it works

- The PyO3 extension compiles the td-rs `tdclient`/`tdutils` crates in through a cargo git dependency pinned to a td-rs commit (see `Cargo.toml`) — no shared library, no separate TDLib build, no system TDLib install.
- The Python surface is TDLib's JSON client: the four functions of the `td_create_client_id` / `td_send` / `td_receive` / `td_execute` C ABI, bytes in, bytes out.
- td-rs is the C++-parity rewrite of TDLib: its JSON client is pinned byte-for-byte against the C++ TDLib behavior, so the bindings inherit C++ semantics exactly.

## Compatibility

The extension builds wherever td-rs builds:

- **Linux** (`x64`, `ARM64`) — glibc 2.17+ (manylinux2014 wheels): RHEL/CentOS 7+, Debian 8+, Ubuntu 13.10+, Fedora 19+
- **Windows** (`x64`) — Windows 7+
- **macOS** (`M-series`) — macOS 11+
- Python **3.10+**

Linux systems older than glibc 2.17 (CentOS 6 / RHEL 6 era) cannot be supported: the Rust toolchain and Python 3.10+ itself both require glibc 2.17 there, the same floor as the original project and TDLib's own wheels.

## Installation

Once published:

```bash
pip install tdjson-rs
```

From source with [maturin](https://github.com/PyO3/maturin):

```bash
pip install maturin
maturin develop --release    # into the current virtualenv
# or build a wheel:
maturin build --release && pip install target/wheels/tdjson_rs-*.whl
```

A C compiler, `perl`, and `make` are needed once, to build the vendored SQLCipher/OpenSSL inside td-rs. The first build compiles the whole td-rs stack; afterwards everything lives in the wheel.

NixOS note: rustc's self-contained `lld` linker wrapper is broken in the nix `rustup` package (rustc 1.90+ enables it by default). Build with `RUSTFLAGS="-C linker-features=-lld"` to use the system linker instead.

## Usage

Here's a quick example to get you started:

```python
import json
import tdjson

# Create a new TDLib client
client_id = tdjson.td_create_client_id()

# Send a request to TDLib
request = {"@type": "getOption", "name": "version"}
tdjson.td_send(client_id, json.dumps(request).encode("utf-8"))

# Receive updates or responses
response = tdjson.td_receive(10.0)
if response:
    print(response)

# Synchronously execute a TDLib request
result = tdjson.td_execute(
    json.dumps(
        {
            "@type": "getTextEntities",
            "text": "@telegram /test_command https://telegram.org telegram.me",
            "@extra": ["5", 7.0, "a"],
        }
    ).encode("utf-8")
)
print(result)
```

For the full login flow, check out [examples/tdjson_example.py](examples/tdjson_example.py) — the TDLib Python example, running unchanged.

API notes:

- Requests are UTF-8 JSON `bytes`; `td_send`/`td_execute` accept exactly the C ABI's contract — invalid JSON comes back as an `error` object (code 400), not an exception. Non-UTF-8 request bytes raise `UnicodeDecodeError`.
- `td_receive(timeout)` returns `bytes` or `None` on timeout, and must not be called simultaneously from two threads (it is the one-receiver C++ contract). Receive loops must tolerate `None`: around a client's close, one `None` arrives before the final `authorizationStateClosed` update (the C++ `ClientManager` wake-up semantics).
- The blocking calls release the GIL, so other Python threads keep running.

## Development

```bash
git clone https://github.com/td-rs/tdjson-rs
cd tdjson-rs
python3 -m venv .venv && . .venv/bin/activate
pip install maturin pytest
maturin develop
pytest tests/
```

`tests/test_api.py` pins the extension contract (execute round-trips, the manager client loop, error objects) to the behaviors td-rs pins byte-for-byte against C++.

To develop against a local td-rs checkout instead of the pinned commit, uncomment the `[patch]` block at the bottom of `Cargo.toml`.

## Versioning

The version tracks the TDLib release the backend pins — `1.8.67` — and appears in `Cargo.toml`, `pyproject.toml`, and `python/tdjson/_version.py`; a test asserts they never drift.

## License

MIT — see [LICENSE](LICENSE). The td-rs backend itself is licensed under BSL-1.0. TDLib is © Telegram and the TDLib authors (Boost Software License 1.0).
