//! `tdjson_ext` — the PyO3 extension behind the `tdjson` Python package.
//!
//! TDLib's JSON client for Python: the four functions of the
//! `td_create_client_id`/`td_send`/`td_receive`/`td_execute` C ABI, backed
//! directly by the td-rs Rust implementation (`tdclient::client_json`)
//! compiled into this module — the extension never touches a
//! `libtdjson.so`. Bytes in, bytes out, `None` instead of the C++ null
//! pointer; the GIL is released around every call that can block.
//!
//! The JSON contract is the C++ one (so the original's): requests must be
//! UTF-8 JSON objects; invalid requests come back as `error` objects, not
//! exceptions (the C++ `ClientJson::to_request` parity), and `td_receive`
//! must not be called simultaneously from two different threads. The one
//! deliberate improvement over the bytes-based C ABI: non-UTF-8 request
//! bytes raise `UnicodeDecodeError` instead of crashing the interpreter.

use pyo3::exceptions::PyUnicodeDecodeError;
use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyBytesMethods, PyModule};

use tdclient::client_json;

/// The request bytes as UTF-8 JSON (the C ABI passes a `char *`).
fn request_json<'a>(request: &'a Bound<'_, PyBytes>) -> PyResult<&'a str> {
    let bytes = request.as_bytes();
    match std::str::from_utf8(bytes) {
        Ok(request) => Ok(request),
        Err(error) => Err(PyUnicodeDecodeError::new_err((
            "utf-8",
            // Owned: the exception args must outlive the call (PyErr is 'static).
            bytes.to_vec(),
            error.valid_up_to(),
            error.valid_up_to() + error.error_len().unwrap_or(1),
            "invalid utf-8",
        ))),
    }
}

/// Returns an opaque identifier of a new TDLib instance.
#[pyfunction]
fn td_create_client_id(py: Python<'_>) -> i32 {
    py.detach(client_json::create_client_id)
}

/// Sends request to the TDLib client. May be called from any thread.
#[pyfunction]
fn td_send(py: Python<'_>, client_id: i32, request: &Bound<'_, PyBytes>) -> PyResult<()> {
    let request = request_json(request)?;
    py.detach(|| client_json::send(client_id, request));
    Ok(())
}

/// Receives incoming updates and request responses. Must not be called
/// simultaneously from two different threads.
#[pyfunction]
fn td_receive<'py>(py: Python<'py>, timeout: f64) -> Option<Bound<'py, PyBytes>> {
    py.detach(|| client_json::receive(timeout))
        .map(|response| PyBytes::new(py, response.as_bytes()))
}

/// Synchronously executes a TDLib request.
#[pyfunction]
fn td_execute<'py>(
    py: Python<'py>,
    request: &Bound<'py, PyBytes>,
) -> PyResult<Option<Bound<'py, PyBytes>>> {
    let request = request_json(request)?;
    let response = py.detach(|| client_json::execute(request));
    Ok(Some(PyBytes::new(py, response.as_bytes())))
}

#[pymodule]
fn tdjson_ext(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(td_create_client_id, module)?)?;
    module.add_function(wrap_pyfunction!(td_send, module)?)?;
    module.add_function(wrap_pyfunction!(td_receive, module)?)?;
    module.add_function(wrap_pyfunction!(td_execute, module)?)?;
    Ok(())
}
