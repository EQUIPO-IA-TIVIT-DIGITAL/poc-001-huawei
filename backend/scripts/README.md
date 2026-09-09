# Utility Scripts

This directory contains supported local utility scripts.

## Files

### enqueue_video.py
Queues a local video-processing job through Redis + RQ.

**Usage:**
```bash
python scripts/enqueue_video.py
```

### seed_demo_user.py
Creates or updates the local SQLite demo account.

```bash
export DEMO_USER_PASSWORD='replace-with-local-demo-password'
python scripts/seed_demo_user.py
```

Credentials: username `demo`; password from `DEMO_USER_PASSWORD`.

### test_rtsp_stream.py
Validates an RTSP stream locally before it is integrated into a video workflow.

## Warning

These scripts are development utilities and must not be included in production images.

## Adding New Scripts

If you need to create a new utility script:

1. Place it in this directory
2. Document it in this README
3. Ensure it is not included in the production Dockerfile
4. Include clear comments about its purpose
