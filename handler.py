"""Minimal RunPod Serverless worker for Casa sem CEP OS lightweight tests."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
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


def _run_transcription_metadata_mock(input_data: dict[str, Any]) -> dict[str, Any]:
    job_id = input_data.get("job_id")
    payload_json = _get_payload_json(input_data)
    episode_id = payload_json.get("episode_id")
    episode_title = str(payload_json.get("episode_title") or "Teste de transcricao mock")
    media_filename = str(payload_json.get("media_filename") or "video_teste.mp4")
    duration_seconds = int(payload_json.get("duration_seconds") or 0)
    language = str(payload_json.get("language") or "pt-BR")

    bucket = os.environ["RUNPOD_STORAGE_BUCKET"]
    txt_key = f"artifacts/transcriptions/job-{job_id}/transcription.txt"
    metadata_key = f"artifacts/transcriptions/job-{job_id}/metadata.json"

    transcription_text = (
        "[00:00:00] Inicio do teste de transcricao mock.\n"
        "[00:00:10] O sistema Casa sem CEP OS esta validando o pipeline.\n"
        "[00:00:20] Este conteudo simula uma transcricao real.\n"
    )
    metadata = {
        "episode_id": episode_id,
        "episode_title": episode_title,
        "media_filename": media_filename,
        "duration_seconds": duration_seconds,
        "language": language,
        "segments": 3,
        "generated_by": "transcription_metadata_mock",
    }

    txt_body = transcription_text.encode("utf-8")
    metadata_body = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")

    s3 = _build_s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=txt_key,
        Body=txt_body,
        ContentType="text/plain; charset=utf-8",
    )
    s3.put_object(
        Bucket=bucket,
        Key=metadata_key,
        Body=metadata_body,
        ContentType="application/json",
    )

    txt_read_back = s3.get_object(Bucket=bucket, Key=txt_key)["Body"].read().decode("utf-8")
    metadata_read_back = json.loads(s3.get_object(Bucket=bucket, Key=metadata_key)["Body"].read().decode("utf-8"))

    return {
        "message": "transcription-metadata-ok",
        "artifact_type": "transcricao_txt",
        "bucket": bucket,
        "object_key": txt_key,
        "content_type": "text/plain",
        "size_bytes": len(txt_body),
        "read_back_ok": txt_read_back == transcription_text and metadata_read_back == metadata,
        "segments": 3,
        "duration_seconds": duration_seconds,
        "language": language,
        "extra_artifacts": [
            {
                "artifact_type": "transcricao_metadata",
                "bucket": bucket,
                "object_key": metadata_key,
                "content_type": "application/json",
                "size_bytes": len(metadata_body),
            }
        ],
    }


def _run_media_upload_test(input_data: dict[str, Any]) -> dict[str, Any]:
    job_id = input_data.get("job_id")
    payload_json = _get_payload_json(input_data)
    media_file_id = payload_json.get("media_file_id") or input_data.get("media_file_id")
    filename = str(payload_json.get("filename") or "media-file")
    mime_type = str(payload_json.get("mime_type") or "application/octet-stream")
    status = str(payload_json.get("status") or "registered")

    bucket = os.environ["RUNPOD_STORAGE_BUCKET"]
    object_key = f"artifacts/media/job-{job_id}/media_metadata.json"
    metadata = {
        "media_file_id": media_file_id,
        "filename": filename,
        "mime_type": mime_type,
        "status": status,
    }
    body = json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8")

    s3 = _build_s3_client()
    s3.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=body,
        ContentType="application/json",
    )
    read_back = json.loads(s3.get_object(Bucket=bucket, Key=object_key)["Body"].read().decode("utf-8"))

    return {
        "message": "media-upload-test-ok",
        "artifact_type": "media_metadata",
        "media_file_id": media_file_id,
        "bucket": bucket,
        "object_key": object_key,
        "content_type": "application/json",
        "size_bytes": len(body),
        "read_back_ok": read_back == metadata,
    }


def _container_format(filename: str, mime_type: str | None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".mov" or mime_type == "video/quicktime":
        return "quicktime_or_unknown"
    if suffix == ".mp4" or mime_type == "video/mp4":
        return "mp4_or_unknown"
    return "unknown"


def _run_metadata_probe(input_data: dict[str, Any]) -> dict[str, Any]:
    payload_json = _get_payload_json(input_data)
    media_file_id = payload_json.get("media_file_id")
    filename = str(payload_json.get("filename") or "media-file")
    mime_type = payload_json.get("mime_type")
    bucket = str(payload_json.get("bucket") or os.environ["RUNPOD_STORAGE_BUCKET"])
    object_key = str(payload_json.get("object_key") or "")
    expected_checksum = payload_json.get("checksum")

    if not object_key:
        raise ValueError("object_key is required for metadata_probe")

    s3 = _build_s3_client()
    digest = hashlib.sha256()
    size_bytes = 0
    with tempfile.NamedTemporaryFile(prefix="metadata-probe-", suffix=Path(filename).suffix, delete=True) as tmp:
        response = s3.get_object(Bucket=bucket, Key=object_key)
        body = response["Body"]
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
            digest.update(chunk)
            size_bytes += len(chunk)
        tmp.flush()

    sha256_value = digest.hexdigest()
    probe = {
        "media_file_id": media_file_id,
        "probe_type": "metadata_probe",
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "sha256": sha256_value,
        "checksum_matches": expected_checksum == sha256_value if expected_checksum else None,
        "extension": Path(filename).suffix,
        "container_format": _container_format(filename, mime_type),
        "duration_seconds": None,
        "video_codec": None,
        "audio_codec": None,
        "width": None,
        "height": None,
        "fps": None,
        "storage_bucket": bucket,
        "storage_object_key": object_key,
        "method": "python_basic",
        "processed_with": "metadata_probe_cpu_no_decode",
    }
    probe_body = json.dumps(probe, ensure_ascii=False, indent=2).encode("utf-8")
    probe_key = f"media/probes/media-{media_file_id}/metadata_probe.json"
    s3.put_object(
        Bucket=bucket,
        Key=probe_key,
        Body=probe_body,
        ContentType="application/json",
    )
    read_back = json.loads(s3.get_object(Bucket=bucket, Key=probe_key)["Body"].read().decode("utf-8"))
    return {
        "message": "metadata-probe-ok",
        "artifact_type": "metadata_probe",
        "media_file_id": media_file_id,
        "bucket": bucket,
        "object_key": probe_key,
        "content_type": "application/json",
        "size_bytes": len(probe_body),
        "read_back_ok": read_back == probe,
        "probe": probe,
    }


def _fps_from_stream(stream: dict[str, Any]) -> float | None:
    value = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    if not value or value == "0/0":
        return None
    if isinstance(value, str) and "/" in value:
        numerator, denominator = value.split("/", 1)
        try:
            denominator_float = float(denominator)
            if denominator_float == 0:
                return None
            return round(float(numerator) / denominator_float, 3)
        except ValueError:
            return None
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _run_ffprobe(local_path: str) -> dict[str, Any]:
    command = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", local_path]
    completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)
    return json.loads(completed.stdout or "{}")


def _run_metadata_probe_ffprobe(input_data: dict[str, Any]) -> dict[str, Any]:
    payload_json = _get_payload_json(input_data)
    media_file_id = payload_json.get("media_file_id")
    filename = str(payload_json.get("filename") or "media-file")
    mime_type = payload_json.get("mime_type")
    bucket = str(payload_json.get("bucket") or os.environ["RUNPOD_STORAGE_BUCKET"])
    object_key = str(payload_json.get("object_key") or "")
    expected_checksum = payload_json.get("checksum")
    if not object_key:
        raise ValueError("object_key is required for metadata_probe_ffprobe")
    s3 = _build_s3_client()
    digest = hashlib.sha256()
    size_bytes = 0
    with tempfile.NamedTemporaryFile(prefix="metadata-ffprobe-", suffix=Path(filename).suffix, delete=True) as tmp:
        response = s3.get_object(Bucket=bucket, Key=object_key)
        body = response["Body"]
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            tmp.write(chunk)
            digest.update(chunk)
            size_bytes += len(chunk)
        tmp.flush()
        ffprobe_json = _run_ffprobe(tmp.name)
    streams = ffprobe_json.get("streams") or []
    format_data = ffprobe_json.get("format") or {}
    video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), {})
    audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), {})
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None
    def _int_or_none(value: Any) -> int | None:
        try:
            return int(float(value)) if value is not None else None
        except (TypeError, ValueError):
            return None
    sha256_value = digest.hexdigest()
    probe = {
        "media_file_id": media_file_id,
        "probe_type": "metadata_probe_ffprobe",
        "filename": filename,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "sha256": sha256_value,
        "checksum_matches": expected_checksum == sha256_value if expected_checksum else None,
        "extension": Path(filename).suffix,
        "format_name": format_data.get("format_name"),
        "format_long_name": format_data.get("format_long_name"),
        "duration_seconds": _float_or_none(format_data.get("duration")),
        "bit_rate": _int_or_none(format_data.get("bit_rate")),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "fps": _fps_from_stream(video_stream),
        "stream_count": len(streams),
        "streams": streams,
        "storage_bucket": bucket,
        "storage_object_key": object_key,
        "method": "ffprobe",
        "processed_with": "ffprobe_metadata_cpu_no_decode",
    }
    probe_body = json.dumps(probe, ensure_ascii=False, indent=2).encode("utf-8")
    probe_key = f"media/probes/media-{media_file_id}/metadata_probe_ffprobe.json"
    s3.put_object(Bucket=bucket, Key=probe_key, Body=probe_body, ContentType="application/json")
    read_back = json.loads(s3.get_object(Bucket=bucket, Key=probe_key)["Body"].read().decode("utf-8"))
    return {
        "message": "metadata-probe-ffprobe-ok",
        "artifact_type": "metadata_probe_ffprobe",
        "media_file_id": media_file_id,
        "bucket": bucket,
        "object_key": probe_key,
        "content_type": "application/json",
        "size_bytes": len(probe_body),
        "read_back_ok": read_back == probe,
        "probe": probe,
    }


def _build_result_json(tipo: str, input_data: dict[str, Any]) -> dict[str, Any]:
    payload_json = _get_payload_json(input_data)
    if tipo == "storage_env_check":
        return _run_storage_env_check()

    if tipo == "storage_test":
        return _run_storage_test(input_data.get("job_id"))

    if tipo == "artifact_text_test":
        return _run_artifact_text_test(input_data)

    if tipo == "transcription_metadata_mock":
        return _run_transcription_metadata_mock(input_data)

    if tipo == "media_upload_test":
        return _run_media_upload_test(input_data)

    if tipo == "metadata_probe":
        return _run_metadata_probe(input_data)

    if tipo == "metadata_probe_ffprobe":
        return _run_metadata_probe_ffprobe(input_data)

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
    except (KeyError, BotoCoreError, ClientError, ValueError, TypeError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
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
