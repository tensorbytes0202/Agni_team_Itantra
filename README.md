# iTantra

## Indian Multilingual TTS & STT Aided Neural Transceiver Radio Access for Low-Bitrate Links.

iTantra is an **offline-first multilingual communication system** designed to enable voice-based communication over **low-bandwidth and low-bitrate communication links**.

Instead of transmitting raw audio, iTantra converts the speaker's voice into text using **offline Speech-to-Text (STT)**, transmits the compact textual representation through a communication channel, and reconstructs the message on the receiver side using **offline Text-to-Speech (TTS)**.

This approach reduces the communication bandwidth required for voice-based communication while preserving a natural **speak-and-listen experience** for the user.

The system is designed especially for scenarios where conventional Internet connectivity or high-bandwidth communication infrastructure may not be available.

---

# 🎯 Problem Statement

Traditional voice communication requires continuous transmission of audio data. In low-bandwidth environments, transmitting raw audio can consume significant network resources and may become unreliable.

This becomes particularly challenging in environments such as:

- 🚨 Disaster and emergency situations
- 🏔️ Remote and mountainous regions
- 📡 Low-bandwidth radio networks
- 🪖 Defence and field operations
- 🚑 Search and rescue operations
- 🌐 Areas with poor or no Internet connectivity
- ⚠️ Network infrastructure failure scenarios

In such environments, there is a need for a communication system that can provide a **voice-like experience without depending on high-bandwidth Internet connectivity**.

---

# 💡 Our Solution

iTantra introduces a **Neural Transceiver architecture** where speech is converted into a compact textual representation before transmission.

### Basic Communication Flow

```text
             SENDER
               │
               ▼
        🎙️ Voice Input
               │
               ▼
      ┌─────────────────┐
      │   Offline STT   │
      │  Speech → Text  │
      └────────┬────────┘
               │
               ▼
       Text Processing
               │
               ▼
      Packet Formation
               │
               ▼
    ┌────────────────────┐
    │ Communication Link │
    │   WiFi / Radio      │
    └─────────┬──────────┘
              │
              ▼
       Packet Reception
              │
              ▼
      Message Reconstruction
              │
              ▼
      ┌─────────────────┐
      │   Offline TTS   │
      │  Text → Speech  │
      └────────┬────────┘
               │
               ▼
        🔊 Voice Output
               │
               ▼
            RECEIVER
