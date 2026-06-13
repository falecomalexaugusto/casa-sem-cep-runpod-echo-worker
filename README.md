# Casa sem CEP RunPod Echo Worker

Minimal RunPod Serverless worker for the Casa sem CEP OS integration test.

This worker exists only to validate:

```text
DigitalOcean -> RunPod Serverless -> callback -> DigitalOcean SQLite
```

## Safety

This worker:

- does not use GPU;
- does not load AI models;
- does not process videos;
- does not process images;
- does not run Whisper;
- does not run Qwen;
- does not run MiniCPM.

## Files

```text
handler.py
requirements.txt
Dockerfile
README.md
.gitignore
```

## Environment Variables

Configure this variable in the RunPod Serverless Endpoint:

```text
RUNPOD_CALLBACK_SECRET=<same value configured in DigitalOcean>
```

Do not commit secrets to Git.

## Test Payload

Use this payload first with an empty callback URL to avoid calling DigitalOcean during the endpoint smoke test:

```json
{
  "input": {
    "job_id": 123,
    "tipo": "echo",
    "payload_json": {
      "message": "ping"
    },
    "callback_url": ""
  }
}
```

Expected response:

```json
{
  "job_id": 123,
  "runpod_request_id": "...",
  "result_json": {
    "message": "pong",
    "echo": true,
    "tipo": "echo"
  },
  "callbacks": {
    "running": null,
    "completed": null
  }
}
```

## Callback Payloads

When `callback_url` is present, the worker sends two callbacks.

Running:

```json
{
  "job_id": 123,
  "status": "running",
  "runpod_request_id": "runpod-job-id"
}
```

Completed:

```json
{
  "job_id": 123,
  "status": "completed",
  "runpod_request_id": "runpod-job-id",
  "result_json": {
    "message": "pong",
    "echo": true,
    "tipo": "echo"
  }
}
```

Header:

```text
X-RunPod-Callback-Secret: <RUNPOD_CALLBACK_SECRET>
```

## RunPod Serverless Setup

Recommended path:

```text
RunPod Console
-> Serverless
-> New Endpoint
-> GitHub Integration
-> Select this repository
-> Branch: main
-> Dockerfile path: Dockerfile
-> Endpoint type: Queue
```

Suggested endpoint name:

```text
casa-sem-cep-echo
```

Scale/cost recommendation:

```text
Min/Active workers: 0
Max workers: 1
Use the cheapest resource available. No GPU is required for this echo worker.
```

## Local Static Validation

Without installing dependencies, you can validate syntax with:

```bash
python3 -m py_compile handler.py
```

## DigitalOcean Configuration Later

Only after the RunPod endpoint is created and smoke-tested, configure the DigitalOcean `.env`:

```text
RUNPOD_MODE=real
RUNPOD_API_URL=https://api.runpod.ai/v2/{ENDPOINT_ID}/run
RUNPOD_API_TOKEN=<real token>
RUNPOD_CALLBACK_URL=https://app.meustatus.com/api/runpod/callback
RUNPOD_CALLBACK_SECRET=<same secret configured in RunPod>
```

## Structured Mock Job

The worker also supports a lightweight structured payload type:

```text
event_candidates_mock
```

Example payload:

```json
{
  "input": {
    "job_id": 999,
    "tipo": "event_candidates_mock",
    "payload_json": {
      "episodio_id": 1,
      "source": "manual",
      "transcription": "short transcript text",
      "chapter": "teste",
      "area": "eletrica",
      "tool": "multimetro",
      "risk": "baixo",
      "notes": "mock"
    },
    "callback_url": ""
  }
}
```

Expected `result_json`:

```json
{
  "summary": "Payload validado com sucesso",
  "echo": true,
  "tipo": "event_candidates_mock",
  "received_fields": 8,
  "transcription_length": 21
}
```

## Storage Test Job

The worker supports a lightweight S3-compatible RunPod Storage validation job:

```text
storage_test
```

Required endpoint environment variables:

```text
RUNPOD_STORAGE_BUCKET=zozga7skni
RUNPOD_STORAGE_ENDPOINT=https://s3api-eu-cz-1.runpod.io
RUNPOD_STORAGE_REGION=eu-cz-1
RUNPOD_STORAGE_ACCESS_KEY=<real value>
RUNPOD_STORAGE_SECRET_KEY=<real value>
```

Example payload:

```json
{
  "input": {
    "job_id": 123,
    "tipo": "storage_test",
    "payload_json": {
      "message": "runpod-storage-test"
    },
    "callback_url": "https://app.meustatus.com/api/runpod/callback"
  }
}
```

Expected `result_json`:

```json
{
  "message": "storage-ok",
  "bucket": "zozga7skni",
  "object_key": "tests/job-123/storage-test.json",
  "read_back_ok": true
}
```

## Storage Environment Check Job

The worker supports a diagnostic job that validates only whether the RunPod endpoint environment variables are visible to the active worker revision.

This job does not access S3, does not use `boto3`, and does not write files. It returns only booleans and never returns secret values.

Job type:

```text
storage_env_check
```

Example payload:

```json
{
  "input": {
    "job_id": 123,
    "tipo": "storage_env_check",
    "payload_json": {},
    "callback_url": "https://app.meustatus.com/api/runpod/callback"
  }
}
```

Expected `result_json` shape:

```json
{
  "RUNPOD_STORAGE_BUCKET": true,
  "RUNPOD_STORAGE_ENDPOINT": true,
  "RUNPOD_STORAGE_REGION": true,
  "RUNPOD_STORAGE_ACCESS_KEY": true,
  "RUNPOD_STORAGE_SECRET_KEY": true
}
```

## Text Artifact Test Job

The worker supports a small real text artifact persistence test for Casa sem CEP OS.

This job does not use GPU, AI models, video, Whisper, Qwen, or MiniCPM. It writes and reads back a small UTF-8 text file in RunPod Storage.

Job type:

```text
artifact_text_test
```

Object path:

```text
artifacts/text/job-<job_id>/transcricao_mock.txt
```

Example payload:

```json
{
  "input": {
    "job_id": 123,
    "tipo": "artifact_text_test",
    "payload_json": {
      "episode_title": "Teste de integração RunPod Storage",
      "artifact_type": "transcricao_mock"
    },
    "callback_url": "https://app.meustatus.com/api/runpod/callback"
  }
}
```

Expected `result_json` shape:

```json
{
  "message": "artifact-text-ok",
  "artifact_type": "transcricao_mock",
  "bucket": "zozga7skni",
  "object_key": "artifacts/text/job-123/transcricao_mock.txt",
  "size_bytes": 180,
  "read_back_ok": true
}
```
