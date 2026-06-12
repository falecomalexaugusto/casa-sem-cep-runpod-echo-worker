"""Minimal RunPod Serverless worker for Casa sem CEP OS lightweight tests."""

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


def _get_payload_json(input_data: dict[str, Any]) -> dict[str, Any]:
    payload_json = input_data.get("payload_json") or {}
    return payload_json if isinstance(payload_json, dict) else {}


def _get_message(input_data: dict[str, Any]) -> str:
    payload_json = _get_payload_json(input_data)
    return str(input_data.get("message") or payload_json.get("message") or "ping")


def _get_transcription(payload_json: dict[str, Any]) -> str:
    value = (
        payload_json.get("transcription")
        or payload_json.get("transcription_text")
        or payload_json.get("transcript")
        or payload_json.get("text")
        or ""
    )
    return str(value)


def _build_result_json(tipo: str, input_data: dict[str, Any]) -> dict[str, Any]:
    payload_json = _get_payload_json(input_data)
    if tipo == "event_candidates_mock":
        transcription = _get_transcription(payload_json)
        return {
            "summary": "Payload validado com sucesso",
            "echo": True,
            "tipo": tipo,
            "received_fields": len(payload_json),
            "transcription_length": len(transcription),
        }

    message = _get_message(input_data)
    return {
        "message": "pong" if message == "ping" else message,
        "echo": True,
        "tipo": tipo,
    }


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

    running_callback = _safe_callback(
        callback_url,
        {
            "job_id": job_id,
            "status": "running",
            "runpod_request_id": runpod_request_id,
        },
    )

    result_json = _build_result_json(tipo, input_data)

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
        "received_fields": result_json.get("received_fields"),
        "transcription_length": result_json.get("transcription_length"),
        "result_json": result_json,
        "callbacks": {
            "running": running_callback,
            "completed": completed_callback,
        },
    }


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
