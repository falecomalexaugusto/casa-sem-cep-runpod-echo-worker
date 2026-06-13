"""Minimal RunPod Serverless worker for Casa sem CEP OS lightweight tests."""

from __future__ import annotations

import json
import os
from typing import Any

import boto3
import requests
import runpod
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError


CALLBACK_SECRET_ENV = "RUNPOD_CALLBACK_SECRET"
CALLBACK_TIMEOUT_SECONDS = 20
STORAGE_ENV_KEYS = (
    "RUNPOD_STORAGE_BUCKET",
    "RUNPOD_STORAGE_ENDPOINT",
    "RUNPOD_STORAGE_REGION",
    "RUNPOD_STORAGE_ACCESS_KEY",
    "RUNPOD_STORAGE_SECRET_KEY",
)


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


def _build_s3_client():
    endpoint = os.environ["RUNPOD_STORAGE_ENDPOINT"]
    region = os.environ.get("RUNPOD_STORAGE_REGION") or "us-east-1"
    access_key = os.environ["RUNPOD_STORAGE_ACCESS_KEY"]
    secret_key = os.environ["RUNPOD_STORAGE_SECRET_KEY"]
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )


def _run_storage_env_check() -> dict[str, bool]:
    return {key: bool(os.environ.get(key)) for key in STORAGE_ENV_KEYS}


def _run_storage_test(job_id: Any) -> dict[str, Any]:
    bucket = os.environ["RUNPOD_STORAGE_BUCKET"]
    object_key = f"tests/job-{job_id}/storage-test.json"
    content = {
        "message": "storage-ok",
        "source": "runpod-worker",
        "job_id": job_id,
    }
    body = json.dumps(content, ensure_ascii=False).encode("utf-8")
    s3 = _build_s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=body,
        ContentType="application/json",
    )
    read_response = s3.get_object(Bucket=bucket, Key=object_key)
    read_back = json.loads(read_response["Body"].read().decode("utf-8"))
    return {
        "message": "storage-ok",
        "bucket": bucket,
        "object_key": object_key,
        "read_back_ok": read_back == content,
    }


def _run_artifact_text_test(input_data: dict[str, Any]) -> dict[str, Any]:
    job_id = input_data.get("job_id")
    payload_json = _get_payload_json(input_data)
    episode_title = str(payload_json.get("episode_title") or "Teste de integração RunPod Storage")
    artifact_type = str(payload_json.get("artifact_type") or "transcricao_mock")
    bucket = os.environ["RUNPOD_STORAGE_BUCKET"]
    object_key = f"artifacts/text/job-{job_id}/transcricao_mock.txt"
    content = (
        "Casa sem CEP OS - Artefato de teste\n\n"
        f"Episodio: {episode_title}\n"
        f"Tipo: {artifact_type}\n"
        "Status: validado\n\n"
        "Este arquivo representa o primeiro artefato textual persistido no RunPod Storage.\n"
    )
    body = content.encode("utf-8")
    s3 = _build_s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=body,
        ContentType="text/plain; charset=utf-8",
    )
    read_response = s3.get_object(Bucket=bucket, Key=object_key)
    read_back = read_response["Body"].read().decode("utf-8")
    return {
        "message": "artifact-text-ok",
        "artifact_type": artifact_type,
        "bucket": bucket,
        "object_key": object_key,
        "size_bytes": len(body),
        "read_back_ok": read_back == content,
    }


def _build_result_json(tipo: str, input_data: dict[str, Any]) -> dict[str, Any]:
    payload_json = _get_payload_json(input_data)
    if tipo == "storage_env_check":
        return _run_storage_env_check()

    if tipo == "storage_test":
        return _run_storage_test(input_data.get("job_id"))

    if tipo == "artifact_text_test":
        return _run_artifact_text_test(input_data)

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

    try:
        result_json = _build_result_json(tipo, input_data)
        status = "completed"
        error_message = None
    except (KeyError, BotoCoreError, ClientError, ValueError, TypeError) as exc:
        result_json = {
            "message": "storage-error" if tipo == "storage_test" else "worker-error",
            "tipo": tipo,
            "error": exc.__class__.__name__,
        }
        status = "failed"
        error_message = f"{exc.__class__.__name__}: {exc}"

    completed_payload = {
        "job_id": job_id,
        "status": status,
        "runpod_request_id": runpod_request_id,
        "result_json": result_json,
    }
    if error_message:
        completed_payload["error_message"] = error_message

    completed_callback = _safe_callback(callback_url, completed_payload)

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
