# 🐱 Purrimeter Defense

A vision-based intrusion detection system for enforcing strict counter boundaries against mischievous kitties.

![Purrimeter Defense](https://img.shields.io/badge/Powered%20by-SAM3-orange) ![Docker](https://img.shields.io/badge/Docker-Ready-blue) ![Python](https://img.shields.io/badge/Python-3.11-green)

## Overview

I have 2 adorable *orange* kittens who love hopping on the counter and snuffling around for things they probably shouldn't eat. This project uses Meta's SAM3 (Segment Anything Model 3) vision model to detect when cats are in forbidden zones and triggers alerts with recordings and deterrent actions.

## Features

- 🎥 **RTSP Camera Integration** - Connect multiple IP cameras
- 🧠 **SAM3 AI Detection** - Segment and detect objects using text prompts
- 📏 **Flexible Rule Engine** - Define rules like "cat over counter" with spatial awareness
- 🚨 **Real-time Alerts** - WebSocket-based live notifications
- 📹 **Smart Recording** - Pre-roll and post-roll capture around trigger events
- 💬 **Discord Integration** - Send alerts and recordings to Discord
- 🔌 **Smart Home Actions** - Trigger Kasa smart plugs for deterrents
- 🎨 **Playful Web UI** - Cat-defense themed dashboard with live feeds

## Quick Start

### Prerequisites

- Docker and Docker Compose
- NVIDIA GPU with CUDA support (for SAM3 inference)
- HuggingFace account with access to [facebook/sam3](https://huggingface.co/facebook/sam3)

### 1. Clone and Configure

```bash
git clone <your-repo-url>
cd Purrimeter-Defense

# Create environment file
cp .env.example .env

# Edit .env with your configuration
# - HF_TOKEN: Your HuggingFace token
# - DISCORD_WEBHOOK_URL: Your Discord webhook (optional)
# - KASA_DEVICE_IP: Your smart plug IP (optional)
```

### 2. Start the System

```bash
docker-compose up -d
```

### 3. Access the Dashboard

Open [http://localhost:3000](http://localhost:3000) in your browser.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Purrimeter Defense                        │
├─────────────────────────────────────────────────────────────────┤
│  Frontend (React + Vite)                                        │
│  ├── Dashboard with live camera feeds                           │
│  ├── Camera configuration                                       │
│  ├── Rule builder                                               │
│  ├── Recording viewer                                           │
│  └── WebSocket for real-time updates                            │
├─────────────────────────────────────────────────────────────────┤
│  Backend (FastAPI)                                              │
│  ├── Pipeline Manager                                           │
│  │   ├── Camera Stream (RTSP → frame buffer)                   │
│  │   ├── SAM3 Service (frame → detections)                     │
│  │   ├── Rule Engine (detections → alerts)                     │
│  │   └── Recording Service (pre-roll + recording)              │
│  ├── Action Service                                             │
│  │   ├── Discord webhook                                        │
│  │   ├── Kasa smart plug                                        │
│  │   ├── HTTP webhook                                           │
│  │   └── Sound playback                                         │
│  └── REST API + WebSocket endpoints                             │
├─────────────────────────────────────────────────────────────────┤
│  Storage                                                        │
│  ├── PostgreSQL (cameras, rules, alerts, recordings metadata)  │
│  ├── Redis (pub/sub, caching)                                  │
│  └── Filesystem (video recordings, thumbnails)                  │
└─────────────────────────────────────────────────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `HF_TOKEN` | HuggingFace token for SAM3 access | Required |
| `DISCORD_WEBHOOK_URL` | Discord webhook for alerts | Optional |
| `KASA_DEVICE_IP` | IP of Kasa smart plug | Optional |
| `RECORDING_PRE_ROLL_SECONDS` | Seconds to capture before alert | 5 |
| `RECORDING_POST_ROLL_SECONDS` | Seconds to capture after alert | 3 |
| `DETECTION_SAMPLE_RATE` | Detection runs per second | 2 |
| `DETECTION_CONFIDENCE_THRESHOLD` | Minimum detection confidence | 0.5 |

## Creating Detection Rules

### Rule Types

1. **Object Detected** - Simple presence detection
   - "Trigger when a cat is visible"

2. **Object in Zone** - Detection within screen region
   - "Trigger when cat enters the kitchen area"

3. **Object Over Object** - Spatial relationships
   - "Trigger when cat is over the counter"
   - "Trigger when cat is on the table"

4. **Object Count** - Quantity thresholds
   - "Trigger when more than 2 cats are visible"

### Example Rule: Cat on Counter

```json
{
  "name": "Cat on Counter Alert",
  "camera_id": "kitchen-cam",
  "primary_target": "cat",
  "secondary_target": "counter",
  "condition_type": "object_over_object",
  "condition_params": {
    "relationship": "over"
  },
  "alert_message": "🐱 Cat detected on counter!",
  "on_alert_start_actions": [
    {
      "type": "discord_webhook",
      "params": { "message": "🚨 CAT ALERT!" }
    },
    {
      "type": "kasa_smart_plug",
      "params": { "action": "pulse" }
    }
  ]
}
```

## API Endpoints

### Cameras
- `GET /api/cameras/` - List all cameras
- `POST /api/cameras/` - Add camera
- `PATCH /api/cameras/{id}` - Update camera
- `DELETE /api/cameras/{id}` - Remove camera

### Rules
- `GET /api/rules/` - List all rules
- `POST /api/rules/` - Create rule
- `GET /api/rules/presets/list` - List preset rules
- `POST /api/rules/presets/{id}/apply` - Apply preset

### Streams
- `GET /api/streams/{camera_id}/mjpeg` - MJPEG video stream
- `WS /api/streams/{camera_id}/ws` - WebSocket video + detections
- `WS /api/streams/alerts` - Real-time alert notifications

### Recordings
- `GET /api/recordings/` - List recordings
- `GET /api/recordings/{id}/video` - Download video
- `DELETE /api/recordings/{id}` - Delete recording

## Development

### Local Development (without Docker)

```bash
# Backend
cd Purrimeter-Defense
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### Adding Custom Actions

Create a new action handler in `backend/services/action_service.py`:

```python
class MyCustomAction(ActionHandler):
    @property
    def action_type(self) -> str:
        return "my_custom_action"
    
    async def execute(self, params: Dict[str, Any]) -> ActionResult:
        # Your logic here
        return ActionResult(
            success=True,
            action_type=self.action_type,
            message="Action executed!",
        )
```

Register it in the `ActionService`:

```python
self._handlers["my_custom_action"] = MyCustomAction()
```

## Hardware Recommendations

### Camera
- Any RTSP-compatible IP camera
- 1080p recommended for best detection
- Wide-angle lens for counter coverage

### Deterrent Ideas
- Compressed air sprayer on smart plug
- Ultrasonic deterrent device
- Motion-activated sprinkler (outdoor)
- Smart speaker for sounds

### GPU
- Minimum: NVIDIA GPU with 4GB VRAM
- Recommended: RTX 3060 or better for real-time inference

## Troubleshooting

### SAM3 Not Loading
1. Ensure you've accepted the model terms on HuggingFace
2. Verify your `HF_TOKEN` is set correctly
3. Check GPU memory availability

### Camera Not Connecting
1. Verify RTSP URL format: `rtsp://user:pass@ip:port/stream`
2. Check camera is accessible from Docker network
3. Try the stream in VLC first

### Recordings Not Saving
1. Check `/app/recordings` volume mount
2. Verify disk space availability
3. Check FFmpeg installation in container

## License

Do whatever the heck you want - Feel free to use for protecting your counters from furry intruders! 🐱
