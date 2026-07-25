import json
import time
import logging
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_interaction_logs import Ai_interaction_logs

logger = logging.getLogger(__name__)


class AIInteractionLogger:
    """Tracks all user interactions with AI features."""

    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.start_time: Optional[float] = None

    def start(self):
        self.start_time = time.time()

    async def log(
        self,
        action_type: str,
        input_summary: str = "",
        output_summary: str = "",
        status: str = "success",
        lead_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Ai_interaction_logs:
        duration_ms = 0
        if self.start_time:
            duration_ms = int((time.time() - self.start_time) * 1000)

        log_entry = Ai_interaction_logs(
            user_id=self.user_id,
            action_type=action_type,
            input_summary=input_summary[:500] if input_summary else "",
            output_summary=output_summary[:1000] if output_summary else "",
            status=status,
            lead_id=lead_id,
            metadata_json=json.dumps(metadata or {}),
            duration_ms=duration_ms,
        )
        self.db.add(log_entry)
        await self.db.commit()
        return log_entry