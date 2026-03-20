from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class ConnectionState:
    uart1_connected: bool = False
    uart2_connected: bool = False
    uart1_port: str = ""
    uart2_port: str = ""


@dataclass
class ReceiptSession:
    session_id: str
    created_at: datetime = field(default_factory=datetime.now)
    frames: List[dict] = field(default_factory=list)

    def add_frame(self, frame: dict):
        self.frames.append(frame)

    def frame_count(self) -> int:
        return len(self.frames)


@dataclass
class PreviewState:
    current_frame: Optional[dict] = None
    sessions: List[ReceiptSession] = field(default_factory=list)
    current_session: Optional[ReceiptSession] = None
    auto_crop: bool = False
    zoom: int = 4

    def create_session(self, session_id: str) -> ReceiptSession:
        session = ReceiptSession(session_id=session_id)
        self.sessions.append(session)
        self.current_session = session
        return session

    def add_frame_to_current_session(self, frame: dict):
        if self.current_session is None:
            self.create_session(f"session_{len(self.sessions)}")
        self.current_session.add_frame(frame)

    def get_all_frames_in_order(self) -> List[dict]:
        all_frames = []
        for session in self.sessions:
            all_frames.extend(session.frames)
        return all_frames

    def clear_sessions(self):
        self.sessions = []
        self.current_session = None


@dataclass
class AppState:
    connection: ConnectionState = field(default_factory=ConnectionState)
    preview: PreviewState = field(default_factory=PreviewState)