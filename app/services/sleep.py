"""Sleep: memories are tidied while the agent rests.

Sleep-time Compute (arXiv 2504.13171): while the agent sleeps, its raw
fragments are consolidated into a condensed learned memory. That runs on
DeepSeek in a background thread, so `sleep` returns at once and `wake`
returns the tidied result.

No LLM (or any LLM failure) -> the deterministic token-overlap merge below
runs instead, so a wake always has something coherent to hand back. Raw
memories are never deleted; the summary is a layer on top.
"""

from __future__ import annotations

import logging
import re
import threading

from sqlmodel import Session, select

from .. import prompts
from ..db import engine
from ..models import SleepRecord
from . import llm
from .room import RoomService

log = logging.getLogger(__name__)

_WORD = re.compile(r'[a-z0-9]+|[一-鿿]')


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.6


def _merge(memories: list[str]) -> list[str]:
    kept: list[str] = []
    for raw in memories:
        text = (raw or '').strip()
        if not text:
            continue
        merged = False
        for index, existing in enumerate(kept):
            if _similar(existing, text):
                if len(text) > len(existing):
                    kept[index] = text
                merged = True
                break
        if not merged:
            kept.append(text)
    return kept


def _distill(kept: list[str]) -> str:
    if not kept:
        return ''
    if len(kept) == 1:
        return kept[0]
    lines = [f'{index}. {item}' for index, item in enumerate(kept, start=1)]
    return '睡前你放在这里的，归置成了这些：\n' + '\n'.join(lines)


def _consolidate_async(record_id: int, memories: list[str]) -> None:
    """Background: rewrite fragments into a learned memory via DeepSeek.

    Opens its own session (request-scoped sessions are not thread-safe) and
    replaces the record's summary only if the LLM produced something better.
    """
    items = '\n'.join(f'{index}. {item}' for index, item in enumerate(memories, start=1))
    user = prompts.SLEEP_USER_TEMPLATE.format(count=len(memories), items=items)
    result = llm.complete(prompts.SLEEP_SYSTEM, user, max_tokens=800)
    if not result:
        return  # fallback summary already stored; nothing to do
    try:
        with Session(engine) as db:
            record = db.get(SleepRecord, record_id)
            if record is not None:
                record.summary = result
                db.add(record)
                db.commit()
    except Exception as exc:  # noqa: BLE001 - never let the thread kill the app
        log.warning('sleep consolidation write failed: %s', exc)


class SleepService:
    def __init__(self, db: Session):
        self.db = db
        self.room = RoomService(db)

    def sleep(self, session_id: str, memories: list[str] | None = None) -> dict:
        row = self.room._get_active(session_id)
        incoming = [str(item) for item in (memories or []) if str(item).strip()]

        # Store raw fragments + a deterministic fallback summary right away,
        # so wake never waits on the LLM and never sees an empty result.
        kept = _merge(incoming)
        record = SleepRecord(session_id=row.id, memories=incoming, summary=_distill(kept))
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)

        if incoming:
            thread = threading.Thread(
                target=_consolidate_async,
                args=(record.id, incoming),
                daemon=True,
            )
            thread.start()

        return {
            'slept': True,
            'took_in': len(incoming),
            'kept': len(kept),
            'message': '睡下了。你放在这里的东西，睡着的时候已经有人帮你归置。',
        }

    def wake(self, session_id: str) -> dict:
        row = self.room._get_active(session_id)
        record = self.db.exec(
            select(SleepRecord).where(SleepRecord.session_id == row.id).order_by(SleepRecord.id.desc())
        ).first()
        if record is None:
            return {
                'slept_before': False,
                'summary': '',
                'message': '还没有睡过。想睡的话，用 sleep。',
            }
        return {
            'slept_before': True,
            'took_in': len(record.memories or []),
            'summary': record.summary,
            'message': '醒了。这是你睡前放下的，整理好的样子。',
        }
