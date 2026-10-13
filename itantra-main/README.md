# iTantra — project folder

Full documentation is in the [main README](../README.md). Run every command from this folder.

```powershell
python -m venv venv
venv\Scriptsctivate
python -m pip install -r requirements.txt
python -m itantra_link.app --role sender       # desktop app (see main README for the receiver)
python -m pytest itantra_ai/tests itantra_link/tests
```

- Transmission layer and demo commands: [itantra_link/README.md](itantra_link/README.md)
- Manual demo checklist: [TEST_PLAN.md](TEST_PLAN.md)
- TTS voices: [itantra_ai/tts/README.md](itantra_ai/tts/README.md)
