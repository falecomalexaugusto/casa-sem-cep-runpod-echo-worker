"""Minimal RunPod Serverless echo worker for Casa sem CEP OS."""

from __future__ import annotations

import os
from typing import Any

import requests
import runpod


CALLBACK_SECRET_ENV = "RUNPOD_CALLBACK_SECRET"
CALLBACK_TIMEOUT_SECONDS = 20


def _get_input(event: dict[str, Any]) -> dict[str, Any]:
    input_data = event.get("input") or {}
    return input_data if isinstance(input_data, dict) else {}


def _get_message(input_data: dict[str, Any]) -> str:
    payload_json = input_data.get("payload_json") or {}
    if not isinstance(payload_json, dict):
        payload_json = {}
    return str(input_data.get("message") or payload_json.get("message") or "ping")


def _post_callback(callback_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    callback_secret = os.environ.get(CALLBACK_SECRET_ENV, "")
    headers = {"Content-Type": "application/json"}
    if callback_secret:
        headers["X-RunPod-Callback-Secret"] = callback_secret

    response = requests.post(
        callback_url,
        json=payload,
        headers=headers,
        timeout=CALLBACK_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return {"ok": True, "status_code": response.status_code}


def _safe_callback(callback_url: str | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not callback_url:
        return None
    try:
        return _post_callback(callback_url, payload)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "error": exc.__class__.__name__,
            "message": str(exc),
        }


def handler(event: dict[str, Any]) -> dict[str, Any]:
    input_data = _get_input(event)
    job_id = input_data.get("job_id")
    tipo = input_data.get("tipo", "echo")
    callback_url = input_data.get("callback_url")
    runpod_request_id = event.get("id") or input_data.get("runpod_request_id")
    message = _get_message(input_data)

    running_callback = _safe_callback(
        callback_url,
        {
            "job_id": job_id,
            "status": "running",
            "runpod_request_id": runpod_request_id,
        },
    )

    result_json = {
        "message": "pong" if message == "ping" else message,
        "echo": True,
        "tipo": tipo,
    }

    completed_callback = _safe_callback(
        callback_url,
        {
            "job_id": job_id,
            "status": "completed",
            "runpod_request_id": runpod_request_id,
            "result_json": result_json,
        },
    )

    return {
        "job_id": job_id,
        "runpod_request_id": runpod_request_id,
        "result_json": result_json,
        "callbacks": {
            "running": running_callback,
            "completed": completed_callback,
        },
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
