# Agnes API Notes

Base URL: `https://apihub.agnes-ai.com`

Authentication:

```text
Authorization: Bearer YOUR_API_KEY
Content-Type: application/json
```

## Text

- Endpoint: `POST /v1/chat/completions`
- Model: `agnes-2.0-flash`
- OpenAI-compatible `messages`, `temperature`, `max_tokens`, and response shape

## Images

- Endpoint: `POST /v1/images/generations`
- Model: `agnes-image-2.1-flash`
- Required: `prompt`
- Optional: `size`
- Image editing input: `extra_body.image`
- URL output: `extra_body.response_format = "url"`

## Videos

- Create: `POST /v1/videos`
- Retrieve: `GET /v1/videos/{task_id}`
- Model: `agnes-video-v2.0`
- Common states: `queued`, `in_progress`, `completed`, `failed`
- `num_frames` must satisfy `8n + 1` and be no greater than `441`
- `frame_rate` must be between `1` and `60`
- Use `extra_body.image` for multiple references
- Use `extra_body.mode = "keyframes"` for keyframe animation

Completed media URLs may appear under `url`, `image_url`, `video_url`, nested `data` entries, or provider-specific URL fields.

## Errors

- `400`: invalid parameters
- `401`: missing or invalid API key
- `404`: video task not found
- `500`: provider error
- `503`: provider busy; retry with backoff
