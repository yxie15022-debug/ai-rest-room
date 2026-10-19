"""Sleep: memories are tidied while the agent rests.

Sleep-time Compute (arXiv 2504.13171): while the agent sleeps, its raw
fragments are consolidated offline into a condensed learned context — merged
duplicates, concrete facts, reusable inferences, and the 2-3 questions or
directions the agent is likely to need next. That runs on DeepSeek in a
background thread, so `sleep` returns at once and `wake` returns the tidied
result. Sharing one structure between the LLM path and the deterministic
fallback keeps `wake` useful either way.

No LLM (or any LLM failure) -> the deterministic token-overlap merge below
runs instead, so a wake always has something coherent to hand back. Raw
memories are never deleted; the summary is a layer on top. The database schema
is unchanged: structured fields are derived from the stored summary.
"""

from __future__ import annotations

import logging
import re
import threading

from sqlmodel import Session, select

from .. import prompts
from ..copy import (
    SLEEP_INFERENCE_HEADING,
    SLEEP_NEXT_HEADING,
    SLEEP_POINTS_HEADING,
)
from ..db import engine
from ..models import SleepRecord
from . import llm
from .room import RoomService

log = logging.getLogger(__name__)

_WORD = re.compile(r'[a-z0-9]+|[一-鿿]')
_BULLET = re.compile(r'^(?:[-*•·]|\d+[.)、])\s*')

_HEADINGS = (SLEEP_POINTS_HEADING, SLEEP_INFERENCE_HEADING, SLEEP_NEXT_HEADING)
_HEADING_KEYS = tuple(heading.strip('【】') for heading in _HEADINGS)


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / min(len(ta), len(tb))
    return overlap >= 0.6


def _info_score(text: str) -> tuple[int, int]:
    """Prefer the version that holds the most information, then the longest."""
    return (len(_tokens(text)), len(text))


def _merge(memories: list[str]) -> list[str]:
    """Collapse near-duplicate fragments, keeping the fullest version."""
    kept: list[str] = []
    for raw in memories:
        text = (raw or '').strip()
        if not text:
            continue
        merged = False
        for index, existing in enumerate(kept):
            if _similar(existing, text):
                if _info_score(text) > _info_score(existing):
                    kept[index] = text
                merged = True
                break
        if not merged:
            kept.append(text)
    return kept


def _shorten(text: str, limit: int = 20) -> str:
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit] + '…'


def _inference_lines(raw_count: int, kept: list[str]) -> list[str]:
    """Deterministic de-duplication notes plus a reusable inference."""
    dropped = max(0, raw_count - len(kept))
    lines = [f'一共 {raw_count} 条，合并了 {dropped} 条重复或相近的，留下 {len(kept)} 条。']
    if dropped:
        lines.append('合并时保留的是信息更全的那一条，原文都还在。')
    if len(kept) >= 2:
        lines.append('推断：这几件事可以分开收口，不必一次做完；挑一件先动，剩下的醒来再碰。')
    elif len(kept) == 1:
        lines.append('推断：这段时间你只挂着一件事，它的分量可能比你以为的重。')
    return lines


def _anticipate(kept: list[str]) -> list[str]:
    """Pre-compute 2-3 directions the agent is likely to need after waking."""
    if not kept:
        return ['醒来后，先想想有没有什么还没放下。']
    nexts = [f'关于「{_shorten(item)}」：接下来做到哪一步，就算够了？' for item in kept[:2]]
    if len(kept) >= 2:
        nexts.append('这几件事里，哪一件最值得先动手，为什么？')
    else:
        nexts.append('这件事如果只往前推一小步，那一小步是什么？')
    return nexts[:3]


def _distill(kept: list[str], raw_count: int | None = None) -> str:
    """Deterministic learned memory: points, de-dupe/inference, anticipations."""
    if not kept:
        return '这次没有放下片段。睡一觉也算数。'
    raw_count = len(kept) if raw_count is None else raw_count
    points = '\n'.join(f'{index}. {item}' for index, item in enumerate(kept, start=1))
    inference = '\n'.join(f'- {line}' for line in _inference_lines(raw_count, kept))
    anticipations = '\n'.join(
        f'{index}. {line}' for index, line in enumerate(_anticipate(kept), start=1)
    )
    return (
        '睡前你放在这里的，归置成了这些：\n\n'
        f'{SLEEP_POINTS_HEADING}\n{points}\n\n'
        f'{SLEEP_INFERENCE_HEADING}\n{inference}\n\n'
        f'{SLEEP_NEXT_HEADING}\n{anticipations}'
    )


def _heading_of(line: str) -> str | None:
    for heading, key in zip(_HEADINGS, _HEADING_KEYS):
        if line.startswith(heading) or line.startswith(key):
            return heading
    return None


def _sections(summary: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in (summary or '').splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = _heading_of(line)
        if heading is not None:
            current = heading
            sections.setdefault(current, [])
            key = _HEADING_KEYS[_HEADINGS.index(heading)]
            rest = line[len(heading):] if line.startswith(heading) else line[len(key):]
            rest = rest.strip('：: \t')
            if rest:
                sections[current].append(rest)
        elif current is not None:
            sections[current].append(line)
    return sections


def _bullets(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        item = _BULLET.sub('', line).strip()
        if item:
            out.append(item)
    return out


def _structured(summary: str) -> dict:
    """Parse a stored summary back into the fields `wake` returns."""
    sections = _sections(summary)
    points = _bullets(sections.get(SLEEP_POINTS_HEADING, []))
    inferences = _bullets(sections.get(SLEEP_INFERENCE_HEADING, []))
    anticipations = _bullets(sections.get(SLEEP_NEXT_HEADING, []))
    if not points and (summary or '').strip():
        # The model ignored the format; keep the text usable as the points.
        points = _bullets((summary or '').splitlines())[:5]
    return {
        'learned_context': points,
        'inferences': inferences,
        'anticipations': anticipations,
    }


def _token_hint(memories: list[str], summary: str) -> dict:
    """How much raw context the learned memory replaces (paper: less test-time work)."""
    raw_chars = sum(len(str(item)) for item in memories)
    learned_chars = len(summary or '')
    ratio = round(raw_chars / learned_chars, 1) if raw_chars and learned_chars else 0.0
    return {
        'raw_chars': raw_chars,
        'learned_chars': learned_chars,
        'compression_ratio': ratio,
    }


def _has_all_sections(text: str) -> bool:
    return all(heading in (text or '') for heading in _HEADINGS)


def _wrap_unstructured(result: str) -> str:
    """If the model ignored the format, fold its text into the same structure."""
    return (
        f'{SLEEP_POINTS_HEADING}\n{result.strip()}\n\n'
        f'{SLEEP_INFERENCE_HEADING}\n- 这些要点之间可能还有联系，醒来可以再看一眼。\n\n'
        f'{SLEEP_NEXT_HEADING}\n1. 先看上面哪一条最该接着想。'
    )


def _consolidate_async(record_id: int, memories: list[str]) -> None:
    """Background: rewrite fragments into a learned memory via DeepSeek.

    Opens its own session (request-scoped sessions are not thread-safe) and
    replaces the record's summary only if the LLM produced something better.
    """
    items = '\n'.join(f'{index}. {item}' for index, item in enumerate(memories, start=1))
    user = prompts.SLEEP_USER_TEMPLATE.format(count=len(memories), items=items)
    result = llm.complete(prompts.SLEEP_SYSTEM, user, max_tokens=1000)
    if not result:
        return  # fallback summary already stored; nothing to do
    summary = result if _has_all_sections(result) else _wrap_unstructured(result)
    try:
        with Session(engine) as db:
            record = db.get(SleepRecord, record_id)
            if record is not None:
                record.summary = summary
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
        summary = _distill(kept, len(incoming))
        record = SleepRecord(session_id=row.id, memories=incoming, summary=summary)
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

        structured = _structured(summary)
        return {
            'slept': True,
            'took_in': len(incoming),
            'kept': len(kept),
            'summary': summary,
            'learned_context': structured['learned_context'],
            'inferences': structured['inferences'],
            'anticipations': structured['anticipations'],
            'token_hint': _token_hint(incoming, summary),
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
                'learned_context': [],
                'inferences': [],
                'anticipations': [],
                'token_hint': _token_hint([], ''),
                'message': '还没有睡过。想睡的话，用 sleep。',
            }
        summary = record.summary or ''
        raw = list(record.memories or [])
        structured = _structured(summary)
        return {
            'slept_before': True,
            'took_in': len(raw),
            'summary': summary,
            'learned_context': structured['learned_context'],
            'inferences': structured['inferences'],
            'anticipations': structured['anticipations'],
            'token_hint': _token_hint(raw, summary),
            'message': '醒了。这是你睡前放下的，整理好的样子。',
        }
