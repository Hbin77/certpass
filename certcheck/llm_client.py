"""AgentStream 챗봇(LLM qwen3.5-122b + RAG 지식베이스)으로 판정 이유 설명과 근거 인용을 만든다.

- 판정 등급은 규칙 엔진이 정본이다. LLM은 등급을 바꾸지 않고, 엔진이 낸 사유·근거를 쉬운 말로 풀어 쓴다.
- 근거 목록(번호·제목·링크)은 엔진 판정과 인증 카드에서 서버가 직접 만든다. LLM 답이 비어도 근거 목록은 그대로 보인다.
- 설정이 없으면 enabled=False, 호출이 실패해도 판정 화면은 그대로다(예외는 잡아 짧은 오류 문자열로 돌려준다).

환경변수 (서버 설정으로만 받음, 사용자 입력으로 주소·챗봇을 바꾸지 않음. Key는 저장소·로그·브라우저에 남기지 않는다)
- AGENTSTREAM_API_KEY: 계정관리 'API 연동'에서 발급한 Key(X-API-Key 헤더). 없으면 설명 기능 끔
- AGENTSTREAM_CHATBOT_ID: 공개한 챗봇 UUID. 없으면 설명 기능 끔
- AGENTSTREAM_BASE_URL: 기본 https://api-gateway.jntp-ax.or.kr/agentstream (뒤에 /open/v1을 붙여 부른다)
- AGENTSTREAM_TIMEOUT: 설명 하나의 전체 제한 시간(초, 기본 60)
호출 순서(AgentStream 'Codex용 연동 가이드' 2026-11-07 확인): POST /open/v1/chatbots/{id}/sessions {"query"} → 201 session_id
→ POST /open/v1/chat-sessions/{session_id}/messages {"message"} → application/x-ndjson 스트림
(assistant.delta·assistant.replace의 content, turn.completed가 정상 종료, turn.failed는 실패, references의 type=rag가 문서 출처).
설명마다 새 세션을 만든다(방문자끼리 세션을 공유하지 않음).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from threading import BoundedSemaphore, Lock

NOTICE = "AI가 판정 근거를 풀어 쓴 참고용 설명입니다. 공식 인증·심사가 아니며, 판정 등급은 규칙 엔진 결과를 따릅니다."
MAX_FINDINGS = 12  # 프롬프트에 싣는 보완 사유 수(불가 → 조건부 순)
MAX_SOURCES = 8
CACHE_SIZE = 600  # 데모 제품 5개 × 인증 56장을 다 담을 만큼
CACHE_FILE = os.environ.get("AGENTSTREAM_CACHE_FILE", "out/explain_cache.json")  # 웹 재시작에도 남게(답·출처만, Key·프롬프트 없음)

_cache: OrderedDict[str, dict] = OrderedDict()
_cache_loaded = False
_lock = Lock()
# AgentStream 외부 채팅·모델은 동시·순간 요청 한도가 있어(초과 시 503·LLM_RATE_LIMITED) 서버에서 동시에 부르는 수를 묶는다


def _load_cache() -> None:
    """파일에는 데모 제품 설명(고정 항목)만 있다. 읽은 항목은 고정으로 둔다."""
    global _cache_loaded
    if _cache_loaded:
        return
    _cache_loaded = True
    try:
        data = json.loads(open(CACHE_FILE, encoding="utf-8").read()) if CACHE_FILE else {}
        for k, v in list(data.items())[-CACHE_SIZE:]:
            if isinstance(v, dict) and isinstance(v.get("text"), str):
                _cache[k] = {**v, "pin": True}
    except (OSError, ValueError):
        pass


def _save_cache() -> None:
    """데모 제품 설명만 파일에 남긴다(사용자가 넣은 처방은 메모리에만, 재시작하면 사라짐)."""
    if not CACHE_FILE:
        return
    try:
        os.makedirs(os.path.dirname(CACHE_FILE) or ".", exist_ok=True)
        tmp = f"{CACHE_FILE}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in _cache.items() if v.get("pin")}, f, ensure_ascii=False)
        os.replace(tmp, CACHE_FILE)
    except OSError as e:
        log.warning("explain cache save failed: %s", type(e).__name__)


def _cache_put(key: str, ans: dict, pin: bool) -> None:
    """고정(데모) 항목은 밀어내지 않는다 — 공개 URL에서 아무 제품이나 많이 보내도 시연용 설명은 남는다."""
    _cache[key] = {**ans, "pin": pin}
    _cache.move_to_end(key)
    while len(_cache) > CACHE_SIZE:
        old = next((k for k, v in _cache.items() if not v.get("pin")), None)
        if old is None:
            break
        _cache.pop(old)
    if pin:
        _save_cache()


_slots = BoundedSemaphore(int(os.environ.get("AGENTSTREAM_MAX_CONCURRENT", "1")))  # 모델 순간 요청 한도(LLM_RATE_LIMITED)가 낮아 1
_waiting = 0  # 슬롯을 기다리는 요청 수. 동기 엔드포인트라 기다리는 동안 서버 스레드를 잡으므로 짧게·적게만 기다린다
log = logging.getLogger("certcheck.llm")  # 단계·상태·Content-Type·경과 시간만 남긴다(Key·질문 원문은 남기지 않음)
HTTP_HINT = {401: "API Key 누락·무효", 403: "챗봇 비공개·다른 워크스페이스·CHAT_INVOKE 권한 없음", 404: "API 주소·챗봇·세션 ID 확인",
             422: "요청 본문 형식 확인", 429: "호출 한도 초과 — 잠시 뒤 다시", 503: "동시 처리 한도 또는 모델 일시 장애 — 잠시 뒤 다시"}
THINK = re.compile(r"<think>.*?</think>", re.S)
KW = re.compile(r"\s*\[kw:[^\]]*\]")


def enabled() -> bool:
    return bool(os.environ.get("AGENTSTREAM_API_KEY", "").strip() and os.environ.get("AGENTSTREAM_CHATBOT_ID", "").strip())


def sources_for(v: dict, card: dict) -> list[dict]:
    """번호 붙은 근거 목록: 엔진 판정의 근거 문구(불가·조건부 사유 순) → 카드의 공개 근거 문서 링크."""
    out, seen = [], set()
    for f in sorted(v.get("findings") or [], key=lambda f: {"fail": 0, "cond": 1, "na": 2}.get(f.get("level"), 3)):
        ev = (f.get("evidence") or "").strip()
        if f.get("level") in ("fail", "cond", "na") and ev and ":" not in ev[:25] and ev not in seen:
            seen.add(ev)  # "formula_known:…" 같은 엔진 내부 값은 빼고 사람이 읽는 조문 문구만
            out.append({"title": ev, "url": None, "kind": "판정 근거"})
    for e in card.get("evidence") or []:
        url = str((e or {}).get("url", ""))
        if url.startswith(("https://", "http://")) and url not in seen:
            seen.add(url)
            title = e.get("title") if e.get("title") and e.get("title") != url else url
            out.append({"title": title, "url": url, "kind": "근거 문서"})
    out = out[:MAX_SOURCES]
    for i, s in enumerate(out, 1):
        s["n"] = i
    return out


LIST_KO = {"banned": "금지", "restricted": "제한"}
# 지식베이스(AgentStream)는 문서를 바꿀 때 밑줄을 지워 꼬리표가 [EUCPNP …]로 저장된다(2026-11-07 실측).
# 서버가 EU_CPNP로 물으면 키워드 검색이 빗나가므로 같은 꼬리표 모양으로 찾게 한다.
TAG_IN = re.compile(r"\[([A-Z0-9][A-Z0-9_]{2,})[\s\]]")  # 본문에는 밑줄이 남기도 한다([KR_CFS_EXPORT …) → kb_tag로 맞춘다
DATE = re.compile(r"(?<!\d)(\d{4})\s*[-.년]\s*(\d{1,2})(?!\d)\s*(?:[-.월]\s*(\d{1,2})(?!\d)\s*일?)?")  # '/'는 규정 번호(2019/1021)라 뺌
PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(%|ppm)")


def kb_tag(card_id: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(card_id).upper())


def tag_match(tag: str | None, want: str) -> bool:
    """잘린 꼬리표(4자 이상)는 앞부분이 같으면 같은 카드로 본다."""
    return bool(tag) and (tag == want or (len(tag) >= 4 and tag != want and want.startswith(tag) and not tag.isdigit()))


def _facts(text: str) -> set[str]:
    """날짜(연-월[-일])·백분율·ppm을 같은 모양으로 뽑는다. '2027 년 6 월 6 일'과 '2027-06-06'이 같게 나온다."""
    out = {f"{y}-{int(m):02d}" + (f"-{int(d):02d}" if d else "") for y, m, d in DATE.findall(text or "") if 1 <= int(m) <= 12}
    out |= {f"{float(n):g}{u}" for n, u in PCT.findall(text or "")}
    return out


REF = re.compile(r"근거\s*(\d{1,2})")


def bad_refs(answer: str, n_sources: int) -> list[int]:
    """설명이 인용한 '(근거 n)' 중 근거 목록(1..n)에 없는 번호. 캐시된 옛 설명에도 돌려줄 때마다 계산한다."""
    return sorted({int(x) for x in REF.findall(answer or "") if not 1 <= int(x) <= n_sources})


def unverified_facts(answer: str, corpus: str) -> list[str]:
    """설명에 나온 날짜·비율 중 요청(판정 사유)과 조회 문서 어디에도 없는 것. 월까지만 맞으면(일 생략) 있는 것으로 본다."""
    have = _facts(corpus)
    months = {f[:7] for f in have if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", f)}
    return sorted(f for f in _facts(answer) if f not in have and not (re.fullmatch(r"\d{4}-\d{2}", f) and f in months))


def ai_lines(ai: dict | None) -> tuple[str, str]:
    """AIStream 숨은 불가 경보를 프롬프트에 넣을 (규칙 문장, 본문 구역). 경보가 없으면 둘 다 빈 문자열.
    줄 머리에 대괄호를 쓰지 않는다(AgentStream이 표로 읽음). 확률은 소수 둘째 자리(캐시 키 안정)."""
    if not ai:
        return "", ""
    near = "; ".join(f"입력 '{n['input'][:60]}' — {LIST_KO.get(n['list_type'], n['list_type'])} 성분 '{n['listed'][:60]}'와 "
                     f"이름 유사도 {n['similarity']:.2f}" for n in ai.get("near") or []) or "없음(함량·CAS 누락 등 입력 불완전)"
    rule = ("6. 'AI 모델 경보'가 있으면 '먼저 할 일' 앞에 'AI 경보:'로 시작하는 한 줄을 쓰세요. 규칙 판정 등급은 그대로이며, "
            "AI 모델은 불가 가능성을 경보한 것뿐이라고 구분하고, 확인할 성분(오탈자 의심이면 올바른 이름과 금지 여부 확인)을 적으세요. "
            "이 줄에는 근거 번호를 붙이지 않아도 됩니다.\n")
    body = (f"\nAI 모델 경보(AIStream 랜덤포레스트, 등급 아님): 불가 가능성 {ai['fail_proba']:.2f} (경보 기준 {ai.get('threshold')})\n"
            f"이름이 비슷한 규제 성분: {near}\n")
    return rule, body


def build_prompt(v: dict, card: dict, product: dict, sources: list[dict], ai: dict | None = None, kb_hint: bool = True) -> str:
    fs = sorted([f for f in v.get("findings") or [] if f.get("level") in ("fail", "cond", "na")],
                key=lambda f: {"fail": 0, "cond": 1, "na": 2}[f["level"]])[:MAX_FINDINGS]
    level = {"fail": "불가 사유", "cond": "보완 필요", "na": "해당 없음 사유"}
    # 줄 머리의 [1]·[불가] 같은 대괄호는 AgentStream이 JSON 표로 읽어 turn.failed(INPUT '분석할 표가 여러 개')가 난다
    # (2026-11-07 실측) → 대괄호 없이 '근거 1:'·'(근거 1)'로 쓴다
    lines = [f"- {level[f['level']]}: {KW.sub('', f.get('message', ''))[:240]}"
             + (f" / 근거: {f['evidence'][:160]}" if f.get("evidence") else "")
             + (f" / 할 일: {f['action'][:120]}" if f.get("action") else "") for f in fs]
    if not lines:
        lines = ["- 보완할 항목 없음: 현재 처방·서류로 요건 충족"]
    claims = ", ".join(map(str, product.get("claims") or [])) or "없음"
    ai_rule, ai_body = ai_lines(ai)
    tag = kb_tag(card.get("id"))
    hint = (f"4-1. 지식베이스에서 이 인증 카드는 꼬리표 '{tag}'로 저장돼 있습니다. 문서를 찾을 때 '{tag} {card.get('name_ko')}'로 찾고, "
            "다른 꼬리표의 카드 내용은 쓰지 마세요.\n") if kb_hint else ""
    src = "\n".join(f"근거 {s['n']}: {s['title']}" + (f" — {s['url']}" if s.get("url") and s["url"] != s["title"] else "")
                    for s in sources) or "없음"
    return f"""당신은 화장품 수출 인증 사전 점검 도우미입니다. 아래 규칙 엔진 판정을 중소기업 실무자가 이해하도록 설명하세요.

규칙:
1. 판정 등급 "{v.get('status')}"은 확정값입니다. 등급을 바꾸거나 다른 등급을 암시하지 마세요.
2. 아래 판정 사유와 지식베이스의 '{card.get('id')}' 인증 요건 카드에 있는 내용만 쓰고, 없는 요건·수치·날짜를 만들지 마세요.
3. 문장 끝에 근거 번호를 (근거 1)처럼 붙이세요. 번호는 아래 '근거 목록'의 번호만 씁니다.
4. '(추정)' 표시가 있는 내용은 "원문 확인 필요"라고 밝히세요.
{hint}4-2. 성분의 농도 한도·경고 문구·부작용은 아래 판정 사유에 있는 것만 쓰세요.
5. 한국어, 존댓말, 6문장 이내. 형식:
왜 이 등급인가: (2~3문장)
먼저 할 일: (1~3개, 한 줄씩 "- "로 시작)
{ai_rule}
인증: {card.get('name_ko')} ({card.get('id')}, 관할 {card.get('jurisdiction')})
제품: {str(product.get('name_kr') or '')[:60]} / 유형 {product.get('product_type') or '-'} / 표방 문구 {claims[:200]}
판정 등급: {v.get('status')}
판정 사유:
{chr(10).join(lines)}
{ai_body}
근거 목록:
{src}
"""


BASE_DEFAULT = "https://api-gateway.jntp-ax.or.kr/agentstream"
TEXT_BLOCKS = {None, "text", "output_text"}  # thinking·reasoning·tool 블록은 답변에 붙이지 않는다


def _base() -> str:
    return (os.environ.get("AGENTSTREAM_BASE_URL", "").strip() or BASE_DEFAULT).rstrip("/") + "/open/v1"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다 — 관문이 로그인 페이지로 돌려도 X-API-Key를 다른 호스트로 다시 보내지 않게."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, f"redirect {code} 거부", headers, fp)


_opener = urllib.request.build_opener(_NoRedirect)


def _post(url: str, payload: dict, timeout: float):
    req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json, application/x-ndjson",
                                          "X-API-Key": os.environ.get("AGENTSTREAM_API_KEY", "").strip()})
    return _opener.open(req, timeout=timeout)


def _content(c) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(x if isinstance(x, str) else str(x.get("text") or "") for x in c
                       if isinstance(x, str) or (isinstance(x, dict) and x.get("type") in TEXT_BLOCKS))
    return ""


class RateLimited(ValueError):
    """turn.failed code=LLM_RATE_LIMITED — 모델 공급자의 순간 요청 한도(여러 팀이 같이 씀, 2026-11-07 실측)."""


def parse_stream(lines) -> dict:
    """NDJSON 줄들 → {text, rag_sources}. turn.failed·종료 이벤트 없는 끝은 ValueError."""
    text, rag, seen, done, tool_failed, docs = "", [], set(), False, False, []
    for raw in lines:
        line = (raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw).strip()
        if line.startswith("data:"):
            line = line[5:].strip()
        if not line or line == "[DONE]":
            continue
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        eid = e.get("event_id")
        if isinstance(eid, str) and eid:
            if eid in seen:
                continue
            seen.add(eid)
        ev = e.get("event")
        if ev == "turn.failed":
            err = RateLimited if e.get("code") == "LLM_RATE_LIMITED" else ValueError
            raise err(f"turn.failed {e.get('category') or ''} {e.get('code') or ''} {_content(e.get('content'))[:120]}".strip())
        if ev == "turn.completed":
            done = True
        if ev == "tool.failed":  # 문서 조회(RAG)가 실패해도 답은 올 수 있다 → 답은 쓰고 '근거 조회 실패'로 표시
            tool_failed = True
        if ev in ("assistant.delta", "assistant.replace") and e.get("type") not in ("tool", "progress"):
            piece = _content(e.get("content")) or (e.get("text") if isinstance(e.get("text"), str) else "")
            text = piece if ev == "assistant.replace" else text + piece
        art = e.get("artifact") if isinstance(e.get("artifact"), dict) else {}
        for d in art.get("documents") or []:  # tool.completed의 RAG 결과(2026-11-07 실측: reference=파일명, evidence.section_title=절 제목)
            if isinstance(d, dict) and d.get("reference"):
                sec = (d.get("evidence") or {}).get("section_title") if isinstance(d.get("evidence"), dict) else None
                rag.append((f"{d['reference']} · {sec}" if sec else str(d["reference"]))[:160])
                # 절 제목은 AgentStream이 잘라 꼬리표가 [EUEC처럼 끊기기도 한다 → 본문의 첫 꼬리표를 먼저 본다
                m = TAG_IN.search(str(d.get("document") or "")) or TAG_IN.search(sec or "")
                docs.append({"ref": str(d["reference"])[:120], "section": str(sec or "")[:160],
                             "tag": kb_tag(m.group(1)) if m else None, "text": str(d.get("document") or "")[:4000]})
        for r in e.get("references") or []:
            if isinstance(r, dict) and r.get("type") == "rag" and r.get("source"):
                rag.append(str(r["source"])[:120])
        ctx = e.get("rag_context") or e.get("context")
        for r in ctx if isinstance(ctx, list) else [ctx] if isinstance(ctx, dict) else []:
            src = isinstance(r, dict) and (r.get("source") or (r.get("metadata") or {}).get("source"))
            if src:
                rag.append(str(src)[:120])
    if not done:
        raise ValueError("turn.completed 없이 응답이 끝남")
    text = THINK.sub("", text).strip()
    return {"text": text[:3000], "rag_sources": list(dict.fromkeys(rag))[:MAX_SOURCES], "tool_failed": tool_failed,
            "docs": docs[:MAX_SOURCES * 2]}


def _step(name: str, url: str, payload: dict, timeout: float):
    """POST 한 번. 단계·상태·Content-Type·경과 시간을 기록하고, HTTP 오류는 원인 안내가 붙은 짧은 문구로 바꾼다.
    로그인 리다이렉트 같은 HTML 응답은 정상으로 받지 않는다. 실패한 POST는 자동으로 다시 보내지 않는다."""
    t = time.monotonic()
    try:
        r = _post(url, payload, timeout)
    except urllib.error.HTTPError as e:
        log.warning("agentstream %s HTTP %s %s %.1fs", name, e.code, e.headers.get("Content-Type", ""), time.monotonic() - t)
        raise RuntimeError(f"{name} HTTP {e.code} ({HTTP_HINT.get(e.code, '응답 오류')})") from None
    ctype = r.headers.get("Content-Type", "")
    log.info("agentstream %s HTTP %s %s %.1fs", name, r.status, ctype, time.monotonic() - t)
    if "html" in ctype.lower():
        r.close()
        raise RuntimeError(f"{name} HTML 응답(로그인 페이지·관문 오류로 보임)")
    return r


class Busy(RuntimeError):
    """앞선 설명 요청이 슬롯을 쓰고 있고 기다리는 요청도 많음 — 서버 스레드를 오래 잡지 않으려고 바로 거절."""


def _lines(resp, deadline: float, timeout: float):
    """NDJSON을 바이트 단위로 읽어 줄로 나눈다. 줄바꿈 없이 아주 느리게 오는 응답에도 전체 제한 시간이 걸린다."""
    buf = b""
    while True:
        if time.monotonic() > deadline:
            raise TimeoutError(f"{timeout:.0f}초 초과")
        chunk = resp.read1(8192)
        if not chunk:
            break
        buf += chunk
        *done, buf = buf.split(b"\n")
        yield from done
        if len(buf) > 1_000_000:
            raise ValueError("줄이 너무 김")
    if buf:
        yield buf


def call(prompt: str, timeout: float, title: str = "CertPass 판정 설명", bot: str | None = None) -> dict:
    """세션 → 메시지 스트림. 슬롯(동시 1)을 짧게만 기다리고, 제한 시간은 슬롯을 얻은 뒤부터 잰다.
    bot: 다른 챗봇(예: AI 검토 챗봇) UUID. 없으면 AGENTSTREAM_CHATBOT_ID(판정 설명 챗봇)."""
    global _waiting
    with _lock:
        if _waiting >= int(os.environ.get("AGENTSTREAM_MAX_WAITING", "3")):
            raise Busy("설명 요청이 밀려 있음")
        _waiting += 1
    try:
        got = _slots.acquire(timeout=float(os.environ.get("AGENTSTREAM_QUEUE_WAIT", "15")))
    finally:
        with _lock:
            _waiting -= 1
    if not got:
        raise Busy("설명 요청이 밀려 있음")
    try:
        deadline = time.monotonic() + timeout
        bot = (bot or os.environ["AGENTSTREAM_CHATBOT_ID"]).strip()
        with _step("sessions", f"{_base()}/chatbots/{bot}/sessions", {"query": title[:100]}, min(15.0, timeout)) as r:
            sid = json.loads(r.read()).get("session_id")
        if not sid or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(sid)):
            raise ValueError("session_id 없음")
        left = deadline - time.monotonic()
        if left < 5:  # 남은 시간으로는 답을 받을 수 없으니 메시지를 보내지 않는다(헛 호출로 한도만 쓰지 않게)
            raise TimeoutError("세션 생성에 시간을 다 씀")
        t = time.monotonic()
        with _step("messages", f"{_base()}/chat-sessions/{sid}/messages", {"message": prompt}, left) as r:
            out = parse_stream(_lines(r, deadline, timeout))
        log.info("agentstream stream done %.1fs chars=%d rag=%d tool_failed=%s", time.monotonic() - t,
                 len(out["text"]), len(out["rag_sources"]), out["tool_failed"])
        return out
    finally:
        _slots.release()


def health(timeout: float = 10) -> dict:
    """GET /chatbots/{id}/health → status·message·checked_at. HTTP 200만으로 정상이라 보지 않고 status를 본다."""
    bot = os.environ.get("AGENTSTREAM_CHATBOT_ID", "").strip()
    req = urllib.request.Request(f"{_base()}/chatbots/{bot}/health", method="GET",
                                 headers={"Accept": "application/json", "X-API-Key": os.environ.get("AGENTSTREAM_API_KEY", "").strip()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"ok": False, "http": e.code, "hint": HTTP_HINT.get(e.code, "응답 오류")}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    return {"ok": d.get("status") == "healthy", "status": d.get("status"), "message": d.get("message"),
            "checked_at": d.get("checked_at"), "embedding_models": d.get("embedding_models")}


SEC_TAG = re.compile(r"\s*\[[^\]]*\]?\s*$")


def group_sources(docs: list[dict], card_id: str) -> dict:
    """조회 문서 중 이 인증 카드 조각만 파일별로 묶는다('파일: 절1, 절2'). 다른 카드 조각은 개수만."""
    want = kb_tag(card_id)
    mine = [d for d in docs if tag_match(d.get("tag"), want)]
    by_file: dict[str, list[str]] = {}
    for d in mine:
        sec = SEC_TAG.sub("", d.get("section") or "").strip() or "본문"
        by_file.setdefault(d["ref"], [])
        if sec not in by_file[d["ref"]]:
            by_file[d["ref"]].append(sec)
    return {"rag_sources": [f"{f}: {', '.join(s)}" for f, s in by_file.items()],
            "rag_target": len(mine), "rag_other": len(docs) - len(mine)}


_calls: dict[str, list[float]] = {}  # 방문자(IP)별 새 설명 호출 시각. "*"는 전체 합
# 7팀 AgentStream LLM 일간 토큰 한도 12M(KST 자정 초기화), 설명 1건이 약 30K 토큰(2026-11-07 실측: 약 390건에 11.6M)
# → 공개 URL에서 하루 새 설명 수를 묶어 발표 전에 할당량이 바닥나지 않게 한다
_day = {"date": None, "n": 0}


def _kst_date() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + 9 * 3600))


def _day_take() -> bool:
    cap = int(os.environ.get("AGENTSTREAM_RATE_PER_DAY", "200"))
    with _lock:
        today = _kst_date()
        if _day["date"] != today:
            _day.update(date=today, n=0)
        if _day["n"] >= cap:
            return False
        _day["n"] += 1
        return True


def _rate_take(client: str | None) -> bool:
    """공개 URL이라 누구나 부를 수 있다 → 새로 만드는 설명(캐시 밖)만 전체 분당·시간당, 방문자별 분당 상한."""
    lim = {"*": (int(os.environ.get("AGENTSTREAM_RATE_PER_MIN", "20")), int(os.environ.get("AGENTSTREAM_RATE_PER_HOUR", "300"))),
           "ip": (int(os.environ.get("AGENTSTREAM_RATE_PER_CLIENT_MIN", "6")), 10 ** 9)}
    now = time.monotonic()
    keys = ["*", f"ip:{client or '-'}"]
    with _lock:
        for k in keys:
            _calls[k] = [t for t in _calls.get(k, []) if now - t < 3600]
        for k in keys:
            per_min, per_hour = lim["*" if k == "*" else "ip"]
            ts = _calls[k]
            if len(ts) >= per_hour or sum(now - t < 60 for t in ts) >= per_min:
                return False
        for k in keys:
            _calls[k].append(now)
        if len(_calls) > 5000:  # 방문자 기록이 끝없이 늘지 않게
            for k in [k for k, v in _calls.items() if not v]:
                _calls.pop(k)
        return True


def _rate_refund(client: str | None) -> None:
    """슬롯이 밀려 AgentStream을 부르지도 못한 요청은 상한에서 되돌린다."""
    with _lock:
        for k in ("*", f"ip:{client or '-'}"):
            if _calls.get(k):
                _calls[k].pop()


def explain(v: dict, card: dict, product: dict, ai=None, *, client: str | None = None, pin: bool = False,
            cache_only: bool = False) -> dict:
    """판정 하나(Verdict.to_dict 모양)의 설명.
    - ai: AIStream 경보 dict, 또는 그것을 돌려주는 함수(캐시에 없을 때만 부른다 — 캐시 응답에 ML 왕복을 붙이지 않게).
    - 캐시 키는 경보를 뺀 프롬프트 해시. 같은 판정이면 ML이 잠깐 실패해도 같은 설명을 다시 쓴다.
    - pin: 데모 제품이면 캐시에서 밀어내지 않고 파일(out/explain_cache.json)에도 남긴다."""
    sources = sources_for(v, card)
    base = {"cert_id": v.get("cert_id"), "status": v.get("status"), "sources": sources, "notice": NOTICE}
    if not enabled():
        return {**base, "enabled": False, "reason": "AgentStream 설명 모델 미연결", "ai_alert": None}
    if v.get("status") == "해당 없음":  # 적용 대상이 아니라는 사유뿐이라 AI 설명을 붙이지 않는다(토큰 절약)
        return {**base, "enabled": False, "reason": "해당 없음 판정은 AI 설명을 생략합니다", "ai_alert": None}
    # 경보 내용(확률)은 키에서 빼되, 경보를 정하는 AIStream 모델 주소·기준값은 넣는다 — 모델·기준을 바꾸면 설명도 새로 만든다
    # 지식베이스를 다시 올리면 AGENTSTREAM_KB_VERSION을 올려 예전 지식베이스로 만든 설명을 쓰지 않게 한다
    # 같은 서빙 주소에 새 모델 버전만 붙는 경우(AIStream 워크플로 재실행)를 위해 AISTREAM_MODEL_VERSION도 넣는다
    ml_ver = (f"{os.environ.get('AISTREAM_URL', '')}|{os.environ.get('AISTREAM_FAIL_THRESHOLD', '')}"
              f"|{os.environ.get('AISTREAM_MODEL_VERSION', '')}"
              f"|kb{os.environ.get('AGENTSTREAM_KB_VERSION', '1')}")
    key = hashlib.sha256(f"{build_prompt(v, card, product, sources, None)}\n{ml_ver}".encode()).hexdigest()
    with _lock:
        _load_cache()
        if key in _cache:
            _cache.move_to_end(key)
            hit = {k: val for k, val in _cache[key].items() if k != "pin"}
            return {**base, **hit, "bad_refs": bad_refs(hit.get("text", ""), len(sources)),
                    "enabled": True, "ok": True, "cached": True}
    if cache_only:  # 저장된 설명만 확인(토큰을 쓰지 않음). 없으면 모델을 부르지 않고 알린다
        return {**base, "enabled": True, "ok": False, "cached": False, "ai_alert": None, "error": "NotCached: 저장된 설명 없음"}
    if not _rate_take(client):
        return {**base, "enabled": True, "ok": False, "ai_alert": None,
                "error": "RateLimit: 설명 요청이 많아 잠시 뒤 다시 시도해 주세요"}
    if not _day_take():
        _rate_refund(client)
        return {**base, "enabled": True, "ok": False, "ai_alert": None,
                "error": "RateLimit: 오늘 새로 만들 수 있는 AI 설명 수를 다 썼습니다(미리 만든 설명은 그대로 나옵니다)"}
    ai = ai() if callable(ai) else ai
    prompt = build_prompt(v, card, product, sources, ai)
    title = f"{card.get('id')} {v.get('status')} 설명"
    timeout = float(os.environ.get("AGENTSTREAM_TIMEOUT", "60"))
    try:
        try:
            raw = call(prompt, timeout, title)
        except RateLimited:  # 답이 만들어지지 않은 실패라 중복 답 걱정이 없다 → 한 번만 쉬었다가 새 세션으로
            time.sleep(float(os.environ.get("AGENTSTREAM_RETRY_WAIT", "3")))
            raw = call(prompt, timeout, title)
        if not raw["text"]:
            raise ValueError("빈 응답")
    except Busy as e:
        _rate_refund(client)
        return {**base, "enabled": True, "ok": False, "ai_alert": ai, "error": f"RateLimit: {e}"}
    except Exception as e:  # 키·주소·모델 장애가 판정 화면을 막지 않게 한다. 오류 문구에 Key가 섞이지 않게 형식·길이만
        return {**base, "enabled": True, "ok": False, "ai_alert": ai, "error": f"{type(e).__name__}: {e}"[:200]}
    docs = raw.pop("docs", [])
    g = group_sources(docs, card.get("id")) if docs else {"rag_target": None, "rag_other": None}
    ans = {**raw, **g, "ai_alert": ai, "unverified": unverified_facts(raw["text"], prompt + "\n".join(d["text"] for d in docs))}
    with _lock:
        _cache_put(key, ans, pin)
    return {**base, **ans, "bad_refs": bad_refs(ans["text"], len(sources)), "enabled": True, "ok": True, "cached": False}


if __name__ == "__main__":  # 실제 호출 확인: .venv/bin/python -m certcheck.llm_client [제품=D3] [인증=EU_ECOLABEL_RINSEOFF]
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not enabled():
        sys.exit("AGENTSTREAM_API_KEY·AGENTSTREAM_CHATBOT_ID 환경변수가 없습니다")
    print("health:", json.dumps(health(), ensure_ascii=False))
    from .app import explain_demo

    t0 = time.monotonic()
    out = explain_demo(sys.argv[1] if len(sys.argv) > 1 else "D3", sys.argv[2] if len(sys.argv) > 2 else "EU_ECOLABEL_RINSEOFF")
    print(f"explain: ok={out.get('ok')} {time.monotonic() - t0:.1f}s error={out.get('error')} rag={out.get('rag_sources')}")
    print(out.get("text", ""))
