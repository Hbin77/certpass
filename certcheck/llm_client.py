"""AgentStream 챗봇(LLM qwen3.5-122b + RAG 지식베이스)으로 판정 이유 설명과 근거 인용을 만든다.

- 판정 등급은 규칙 엔진이 정본이다. LLM은 등급을 바꾸지 않고, 엔진이 낸 사유·근거를 쉬운 말로 풀어 쓴다.
- 근거 목록(번호·제목·링크)은 엔진 판정과 인증 카드에서 서버가 직접 만든다. LLM 답이 비어도 근거 목록은 그대로 보인다.
- 설정이 없으면 enabled=False, 호출이 실패해도 판정 화면은 그대로다(예외는 잡아 짧은 오류 문자열로 돌려준다).

환경변수 (서버 설정으로만 받음, 사용자 입력으로 주소를 바꾸지 않음. Key는 저장소·로그에 남기지 않는다)
- AGENTSTREAM_URL: 챗봇 호출 전체 주소. 없으면 설명 기능 끔
- AGENTSTREAM_KEY: API Key
- AGENTSTREAM_AUTH_HEADER: Key를 실을 헤더(기본 Authorization). Authorization이면 값 앞에 "Bearer "를 붙인다
- AGENTSTREAM_QUERY_FIELD: 질문을 담는 본문 필드 이름(기본 query)
- AGENTSTREAM_EXTRA: 본문에 함께 보낼 고정 필드(JSON 객체, 예: {"stream": false})
- AGENTSTREAM_TIMEOUT: 초(기본 60)
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from collections import OrderedDict
from threading import Lock

NOTICE = "AI가 판정 근거를 풀어 쓴 참고용 설명입니다. 공식 인증·심사가 아니며, 판정 등급은 규칙 엔진 결과를 따릅니다."
MAX_FINDINGS = 12  # 프롬프트에 싣는 보완 사유 수(불가 → 조건부 순)
MAX_SOURCES = 8
CACHE_SIZE = 256

_cache: OrderedDict[str, dict] = OrderedDict()
_lock = Lock()
THINK = re.compile(r"<think>.*?</think>", re.S)
KW = re.compile(r"\s*\[kw:[^\]]*\]")


def enabled() -> bool:
    return bool(os.environ.get("AGENTSTREAM_URL", "").strip())


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


def build_prompt(v: dict, card: dict, product: dict, sources: list[dict]) -> str:
    fs = sorted([f for f in v.get("findings") or [] if f.get("level") in ("fail", "cond", "na")],
                key=lambda f: {"fail": 0, "cond": 1, "na": 2}[f["level"]])[:MAX_FINDINGS]
    level = {"fail": "불가 사유", "cond": "보완 필요", "na": "해당 없음 사유"}
    lines = [f"- [{level[f['level']]}] {KW.sub('', f.get('message', ''))[:240]}"
             + (f" / 근거: {f['evidence'][:160]}" if f.get("evidence") else "")
             + (f" / 할 일: {f['action'][:120]}" if f.get("action") else "") for f in fs]
    if not lines:
        lines = ["- 보완할 항목 없음(현재 처방·서류로 요건 충족)"]
    claims = ", ".join(map(str, product.get("claims") or [])) or "없음"
    src = "\n".join(f"[{s['n']}] {s['title']}" + (f" ({s['url']})" if s.get("url") else "") for s in sources) or "(없음)"
    return f"""당신은 화장품 수출 인증 사전 점검 도우미입니다. 아래 규칙 엔진 판정을 중소기업 실무자가 이해하도록 설명하세요.

규칙:
1. 판정 등급 "{v.get('status')}"은 확정값입니다. 등급을 바꾸거나 다른 등급을 암시하지 마세요.
2. 아래 판정 사유와 지식베이스의 '{card.get('id')}' 인증 요건 카드에 있는 내용만 쓰고, 없는 요건·수치·날짜를 만들지 마세요.
3. 문장 끝에 근거 번호를 [1]처럼 붙이세요. 번호는 아래 '근거 목록'의 번호만 씁니다.
4. '(추정)' 표시가 있는 내용은 "원문 확인 필요"라고 밝히세요.
5. 한국어, 존댓말, 6문장 이내. 형식:
왜 이 등급인가: (2~3문장)
먼저 할 일: (1~3개, 한 줄씩 "- "로 시작)

인증: {card.get('name_ko')} ({card.get('id')}, 관할 {card.get('jurisdiction')})
제품: {str(product.get('name_kr') or '')[:60]} / 유형 {product.get('product_type') or '-'} / 표방 문구 {claims[:200]}
판정 등급: {v.get('status')}
판정 사유:
{chr(10).join(lines)}

근거 목록:
{src}
"""


def _headers() -> dict:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("AGENTSTREAM_KEY", "").strip()
    if key:
        name = os.environ.get("AGENTSTREAM_AUTH_HEADER", "Authorization").strip() or "Authorization"
        h[name] = f"Bearer {key}" if name.lower() == "authorization" and not key.lower().startswith("bearer ") else key
    return h


def _body(prompt: str) -> bytes:
    extra = json.loads(os.environ.get("AGENTSTREAM_EXTRA", "") or "{}")
    if not isinstance(extra, dict):
        raise ValueError("AGENTSTREAM_EXTRA는 JSON 객체여야 합니다")
    return json.dumps({**extra, os.environ.get("AGENTSTREAM_QUERY_FIELD", "query") or "query": prompt},
                      ensure_ascii=False).encode()


def _dig(d, keys: tuple[str, ...]):
    """중첩 응답에서 처음 나오는 문자열 답을 찾는다(data.answer, result.content, choices[0].message.content 등)."""
    if isinstance(d, str):
        return d
    if isinstance(d, list):
        return next((x for x in (_dig(i, keys) for i in d) if x), None)
    if not isinstance(d, dict):
        return None
    for k in keys:
        if isinstance(d.get(k), str) and d[k].strip():
            return d[k]
    for k in ("data", "result", "output", "response", "message", "choices", "delta"):
        if isinstance(d.get(k), (dict, list)):
            found = _dig(d[k], keys)
            if found:
                return found
    return None


def parse_answer(body: bytes | str) -> dict:
    """챗봇 응답 → {text, rag_sources}. JSON이 아니면 SSE(data: …) 줄을 이어 붙이고, 그것도 아니면 본문 글자 그대로."""
    raw = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    keys = ("answer", "content", "text", "output_text", "response", "message", "reply", "result")
    try:
        d = json.loads(raw)
    except ValueError:
        parts = []
        for line in raw.splitlines():
            if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
                chunk = line[5:].strip()
                try:
                    parts.append(_dig(json.loads(chunk), keys) or "")
                except ValueError:
                    parts.append(chunk)
        d, text = None, "".join(parts) if parts else raw
    else:
        text = _dig(d, keys) or ""
    rag = []
    if isinstance(d, dict):
        pool = [d] + [d[k] for k in ("data", "result") if isinstance(d.get(k), dict)]
        for x in pool:
            for k in ("sources", "references", "citations", "documents", "source_documents", "contexts"):
                if isinstance(x.get(k), list):
                    for s in x[k][:MAX_SOURCES]:
                        if isinstance(s, dict):
                            name = s.get("title") or s.get("file_name") or s.get("filename") or s.get("source") or s.get("name")
                            if name:
                                rag.append(str(name)[:120])
                        elif isinstance(s, str):
                            rag.append(s[:120])
    text = THINK.sub("", text).strip()
    return {"text": text[:3000], "rag_sources": list(dict.fromkeys(rag))}


def call(prompt: str, timeout: float) -> dict:
    req = urllib.request.Request(os.environ["AGENTSTREAM_URL"].strip(), data=_body(prompt), headers=_headers(), method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return parse_answer(r.read())


def explain(v: dict, card: dict, product: dict) -> dict:
    """판정 하나(Verdict.to_dict 모양)의 설명. 같은 판정·같은 프롬프트는 캐시에서 돌려준다."""
    sources = sources_for(v, card)
    base = {"cert_id": v.get("cert_id"), "status": v.get("status"), "sources": sources, "notice": NOTICE}
    if not enabled():
        return {**base, "enabled": False, "reason": "AgentStream 설명 모델 미연결"}
    prompt = build_prompt(v, card, product, sources)
    key = hashlib.sha256(prompt.encode()).hexdigest()
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return {**base, **_cache[key], "enabled": True, "ok": True, "cached": True}
    try:
        ans = call(prompt, float(os.environ.get("AGENTSTREAM_TIMEOUT", "60")))
        if not ans["text"]:
            raise ValueError("빈 응답")
    except Exception as e:  # 키·주소·모델 장애가 판정 화면을 막지 않게 한다. 오류 문구에 Key가 섞이지 않게 형식·길이만
        return {**base, "enabled": True, "ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    with _lock:
        _cache[key] = ans
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return {**base, **ans, "enabled": True, "ok": True, "cached": False}
