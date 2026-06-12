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
