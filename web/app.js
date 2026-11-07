/* certcheck 화면 — 빌드 없는 바닐라 JS.
 * API는 반드시 상대경로(api/...)로 부른다: 대회 프록시 접두사(/i/<토큰>) 아래에서도 그대로 동작한다.
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ 상수
  const ST = { FAIL: '불가', COND: '조건부', PASS: '통과 가능', NA: '해당 없음' };
  const STATUS_LIST = [
    { s: ST.FAIL, key: 'fail', icon: 'i-fail', def: '재처방해야만 통과' },
    { s: ST.COND, key: 'cond', icon: 'i-cond', def: '재처방 없이 서류·현지책임자·문구·시험 보완으로 통과' },
    { s: ST.PASS, key: 'pass', icon: 'i-pass', def: '현재 상태로 통과' },
    { s: ST.NA, key: 'na', icon: 'i-na', def: '적용 대상 아님' },
  ];
  const STATUS_BY = Object.fromEntries(STATUS_LIST.map((x) => [x.s, x]));
  const RANK = { [ST.FAIL]: 0, [ST.COND]: 1, [ST.PASS]: 2, [ST.NA]: 3 };

  const JUR = {
    KR: '대한민국', EU: '유럽연합', UK: '영국', US: '미국', CA: '캐나다', MX: '멕시코', BR: '브라질', AR: '아르헨티나',
    CO: '콜롬비아', PE: '페루', CL: '칠레', CN: '중국', HK: '홍콩', TW: '대만', JP: '일본', MN: '몽골', ASEAN: '아세안',
    SG: '싱가포르', MY: '말레이시아', TH: '태국', VN: '베트남', ID: '인도네시아', PH: '필리핀', MM: '미얀마', KH: '캄보디아',
    LA: '라오스', BN: '브루나이', IN: '인도', SA: '사우디아라비아', AE: '아랍에미리트', GCC: '걸프협력회의', QA: '카타르',
    KW: '쿠웨이트', OM: '오만', BH: '바레인', TR: '튀르키예', IR: '이란', IL: '이스라엘', EG: '이집트', MA: '모로코',
    ZA: '남아프리카공화국', NG: '나이지리아', EAEU: '유라시아경제연합', RU: '러시아', KZ: '카자흐스탄', UA: '우크라이나',
    AU: '호주', NZ: '뉴질랜드', GLOBAL: '국제(민간)', COMPANY: '회사 단위',
  };
  const JUR_ORDER = ['KR', 'EU', 'UK', 'US', 'CN', 'JP', 'TW', 'HK', 'ASEAN', 'SG', 'MY', 'TH', 'VN', 'ID', 'PH', 'MM', 'KH',
    'LA', 'BN', 'CA', 'MX', 'BR', 'AR', 'CO', 'PE', 'CL', 'SA', 'AE', 'GCC', 'QA', 'KW', 'OM', 'BH', 'TR', 'IR', 'IL', 'EG',
    'MA', 'ZA', 'NG', 'IN', 'EAEU', 'RU', 'KZ', 'UA', 'MN', 'AU', 'NZ', 'GLOBAL', 'COMPANY'];
  const KIND = {
    mandatory_registration: '필수 등록·신고', mandatory_compliance: '필수 준수(규제)', voluntary_certification: '민간 인증',
    marketing_label: '마케팅 표시 인증', company_certification: '회사 인증', packaging: '포장 규제',
    chemical_registration: '화학물질 등록',
  };
  const NATIONAL = new Set(['mandatory_registration', 'mandatory_compliance', 'chemical_registration', 'packaging']);
  const PRIVATE = new Set(['voluntary_certification', 'marketing_label']);
  const FILTERS = [
    { id: 'all', label: '전체', test: () => true },
    { id: 'strategic', label: '중기부 전략인증', test: (c) => !!c.strategic_kr },
    { id: 'national', label: '국가 등록', test: (c) => NATIONAL.has(c.kind) && c.jurisdiction !== 'KR' },
    { id: 'private', label: '민간 인증', test: (c) => PRIVATE.has(c.kind) },
    { id: 'domestic', label: '국내 필수', test: (c) => c.jurisdiction === 'KR' && !PRIVATE.has(c.kind) && c.kind !== 'company_certification' },
  ];

  const CLAIM_LABEL = {
    whitening: '미백', anti_wrinkle: '주름개선', sunscreen: '자외선 차단', moisturizing: '보습', natural: '천연 유래',
    natural_origin_ingredients: '천연 유래 성분', organic: '유기농', acne: '여드름성 피부', antibacterial: '항균',
    anti_hair_loss: '탈모 증상 완화', hair_loss: '탈모 증상 완화', hair_dye: '염모', perm: '펌', hypoallergenic: '저자극',
    free_from_denigrating: '무첨가(○○ 프리)', free_from_informative: '무첨가(정보형)', medical: '의료 효능', halal: '할랄',
    vegan: '비건', children: '어린이용', new_efficacy: '신규 효능', barrier_repair: '장벽 개선', skin_barrier: '피부 장벽',
    deep_cleansing: '딥 클렌징', makeup_removal: '메이크업 제거', all_in_one: '올인원', free_from_21: '21가지 무첨가',
    paraben_free: '파라벤 무첨가', silicone_free: '실리콘 무첨가', skin_irritation_tested: '피부 자극 시험 완료',
    cleansing: '세정', radiance: '광채', pearl_protein_minerals: '진주 단백질·미네랄', marine_bio_wando: '완도 해양 원료',
    whitening_planned: '미백(예정)', cruelty_free: '동물실험 안 함',
  };
  const TEST_LABEL = {
    stability: '안정성', challenge_test: '보존력(챌린지)', microbiology: '미생물', microbial_limit: '미생물 한도',
    heavy_metals: '중금속', physicochemical: '이화학', toxicology: '독성', local_lab_test: '현지 시험기관 시험',
    efficacy_human: '인체 효능', packaging_compatibility: '용기 적합성', packaging_heavy_metals: '포장재 중금속',
    porcine_dna: '돼지 DNA', spf: 'SPF', pa: 'PA', skin_irritation: '피부 자극', eye_irritation: '눈 자극',
    dioxane: '1,4-다이옥산', nitrosamine: '니트로사민',
  };
  const ATTR_NAME = { VEGAN: '비건', V_LABEL: '비건', HALAL: '할랄', NATURAL: '천연·유기농', NATRUE: 'NATRUE' };
  const PTYPE = {
    cleanser_balm: '클렌징 밤', cleanser_foam: '클렌징 폼', face_cream: '크림', sheet_mask: '시트 마스크', serum: '세럼',
    toner: '토너', lotion: '로션', essence: '에센스', sunscreen: '선크림', cosmetic: '화장품',
    cleanser_gel: '클렌징 젤', cleanser_oil: '클렌징 오일', cleansing_water: '클렌징 워터', makeup_remover: '메이크업 리무버',
    shampoo: '샴푸', conditioner: '컨디셔너', body_wash: '바디워시', hand_wash: '핸드워시', soap: '비누',
    rinse_off: '씻어내는 제품', leave_on: '바르는 제품', hair_dye: '염모제', perm: '펌제',
  };
  const FORMULA = {
    full_with_concentration: '함량 있음', ingredients_only_no_concentration: '함량 없음',
    partial_concentration: '일부 함량', concept_only: '처방 미확정',
  };

  // 직접 입력 선택지 — 값은 인증 카드(claim_rules)와 판정 엔진이 쓰는 코드
  const CLAIM_OPTS = [
    ['whitening', '미백'], ['anti_wrinkle', '주름개선'], ['sunscreen', '자외선 차단'], ['moisturizing', '보습'],
    ['natural', '천연 유래'], ['organic', '유기농'], ['acne', '여드름성 피부'], ['antibacterial', '항균'],
    ['anti_hair_loss', '탈모 증상 완화'], ['hair_dye', '염모'], ['hypoallergenic', '저자극'], ['free_from_denigrating', '○○ 프리(무첨가)'],
  ];
  const FUNCTIONAL = new Set(['whitening', 'anti_wrinkle', 'sunscreen', 'anti_hair_loss', 'acne', 'hair_dye']);
  const DOC_OPTS = [
    ['formula_composition_with_percent', '처방 구성표(함량 포함)'],
    ['formula_ingredient_statement', '제조사 전성분 확인서'],
    ['ingredient_list', '전성분표'],
    ['finished_product_test_report', '완제품 시험성적서(중금속·미생물)'],
    ['stability_test_report', '안정성 시험 성적서'],
    ['challenge_test_report', '보존력 시험 성적서'],
    ['msds', 'MSDS'],
    ['label_kr', '국문 라벨'],
    ['skin_irritation_test', '피부 자극 시험'],
    ['functional_report', '기능성 보고·심사 서류'],
    ['packaging_spec', '포장 사양서'],
    ['manufacturer_registration', '제조업 등록증'],
  ];
  const MFR_OPTS = [['CGMP', '제조소 CGMP·ISO 22716'], ['HALAL', '제조소 할랄 인증']];

  // 엔진(classify.GAP_TYPES)과 같은 접두사 규칙 → 화면의 5칸
  const GAP_TYPES = [
    ['ING_BANNED_WITH_EXCEPTION', '성분 확인'], ['ING_BANNED', '재처방'], ['ING_OVER_LIMIT', '재처방'], ['ATTR_', '원료 증명'], ['SILOXANE_BANNED', '재처방'],
    ['SILOXANE_RINSEOFF', '재처방'], ['SILOXANE_D4', '재처방'], ['SILOXANE_SUNSET', '재처방(기한)'], ['SILOXANE_MIX', '성분 확인'],
    ['SILOXANE_PCT', '처방 확정'], ['DOC_DRAFTABLE', '서류(자동 초안)'], ['DOC_', '서류'], ['TEST_', '시험'],
    ['LOCAL_ENTITY', '현지 책임자'], ['LABEL_', '라벨'], ['ALLERGEN_', '라벨'], ['CLAIM_', '표방 문구'],
    ['HALAL_FACILITY', '제조소 확인'], ['FORMULA_', '처방 확정'], ['ING_UNDEFINED', '처방 확정'], ['ING_', '성분 확인'],
    ['PACKAGING', '포장재'], ['PROP65', '성분 확인'], ['COMPANY_', '회사 요건'],
  ];
  const GAP_COL_OF = {
    '재처방': 'reform', '재처방(기한)': 'reform', '서류': 'docs', '서류(자동 초안)': 'docs', '원료 증명': 'docs', '제조소 확인': 'docs',
    '처방 확정': 'docs', '성분 확인': 'docs', '포장재': 'docs', '회사 요건': 'docs', '기타': 'docs',
    '현지 책임자': 'local', '라벨': 'label', '표방 문구': 'label', '시험': 'test',
  };
  const GAP_COLS = [
    { id: 'reform', label: '재처방', lines: ['재처방'], icon: 'i-flask' },
    { id: 'docs', label: '서류·확인', lines: ['서류·', '확인'], icon: 'i-file' },
    { id: 'local', label: '현지 책임자', lines: ['현지', '책임자'], icon: 'i-user' },
    { id: 'label', label: '문구·라벨', lines: ['문구·', '라벨'], icon: 'i-tag' },
    { id: 'test', label: '시험', lines: ['시험'], icon: 'i-tube' },
  ];
  const COL_RANK = { reform: 0, label: 1, docs: 2, test: 3, local: 4 };
  const PLAIN_GAPS = new Set(['서류', '시험', '현지 책임자', '재처방']); // 열 제목과 같아 태그를 달지 않는 분류
  const CONF_CODES = new Set(['ING_PROXY', 'ING_CN_SPEC_2015', 'ING_JP_NAME_ONLY', 'ING_NO_DATA', 'FORMULA_CONCEPT']);

  const DOCS = [
    { id: 'inci_list', name: 'INCI 전성분표', desc: '영문 INCI 전성분과 함량을 함량 순으로 정리합니다.' },
    { id: 'label_draft', name: '수출 라벨 초안', desc: '나라별 표시사항(성분·용량·책임자·경고문) 초안입니다.' },
    { id: 'cpnp_sheet', name: 'EU CPNP 신고 정보 시트', desc: 'CPNP 신고에 넣을 제품·성분·책임자 항목을 모읍니다.' },
    { id: 'mocra_sheet', name: '미국 MoCRA 등록 정보 시트', desc: 'FDA 시설등록·제품리스팅에 넣을 항목을 모읍니다.' },
    { id: 'gap_checklist', name: '보완 체크리스트', desc: '판정 결과의 해야 할 일을 서류·담당자별로 정리합니다.' },
    { id: 'support_program', name: '중기부 지원사업 신청 메모', desc: '해외규격인증 지원 대상 인증과 준비 서류를 정리합니다.' },
  ];

  // ------------------------------------------------------------------ 상태
  const S = {
    health: null, certs: [], certIndex: {}, demo: null, company: {}, explain: {}, explainGen: 0,
    docTypes: null, docMeta: {},
    product: null, result: null, source: null, demoId: null,
    filter: 'all', expanded: new Set(), fill: null, ctrl: null, trigger: null, retry: null, ids: new Map(),
  };

  // ------------------------------------------------------------------ 도우미
  const $ = (sel, root) => (root || document).querySelector(sel);
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ESC[c]);
  const icon = (id, cls) => `<svg class="ic ${cls || ''}" aria-hidden="true" focusable="false"><use href="#${id}"/></svg>`;
  const safeId = (s) => String(s).replace(/[^A-Za-z0-9_-]/g, '_');
  // cert_id마다 겹치지 않는 DOM id (EU/CPNP·EU-CPNP처럼 safeId가 같아지는 경우 대비)
  const rowId = (certId) => { if (!S.ids.has(certId)) S.ids.set(certId, `r${S.ids.size}`); return S.ids.get(certId); };
  const reduceMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const wide = () => window.matchMedia('(min-width: 1024px)').matches;
  const jurName = (j) => JUR[j] || j || '기타';
  const today = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  };
  function announce(msg) {
    const live = $('#live');
    live.textContent = '';
    window.setTimeout(() => { live.textContent = msg; }, 60);
  }

  class ApiError extends Error {
    constructor(status, detail) { super(detail || `오류 ${status}`); this.status = status; this.detail = detail; }
  }
  async function readError(res) {
    let detail = '';
    const type = res.headers.get('content-type') || '';
    try {
      if (type.includes('json')) {
        const body = await res.json();
        const d = body && body.detail;
        if (typeof d === 'string') detail = d;
        else if (Array.isArray(d)) detail = d.map((x) => `${(x.loc || []).slice(1).join('.')} ${x.msg || ''}`.trim()).join(', ');
      } else {
        const text = (await res.text()).trim();
        if (text && text.length <= 120 && !text.includes('<')) detail = text; // HTML 오류 페이지는 보여 주지 않는다
      }
    } catch (e) { /* 본문이 없으면 상태 코드만 쓴다 */ }
    return new ApiError(res.status, detail);
  }
  async function getJSON(path, opts) {
    const res = await fetch(path, Object.assign({ headers: { Accept: 'application/json' } }, opts));
    if (!res.ok) throw await readError(res);
    return res.json();
  }
  async function postJSON(path, body, opts) {
    const res = await fetch(path, Object.assign({
      method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body),
    }, opts));
    if (!res.ok) throw await readError(res);
    return res;
  }
  function explain(err) {
    if (err && err.name === 'AbortError') return '';
    if (err instanceof ApiError) {
      if (err.status === 503) return err.detail || '판정 기준(인증 요건 카드)이 아직 준비되지 않았습니다.';
      if (err.status === 422) return `입력값을 확인하세요. ${err.detail}`.trim();
      if (err.status === 404) return '판정 서버(API)를 찾지 못했습니다. 서버가 실행 중인지, 주소가 맞는지 확인하세요. (오류 404)';
      if (err.status === 405 || err.status === 501) return `이 주소의 서버가 판정 요청을 받지 않습니다. API 서버 주소를 확인하세요. (오류 ${err.status})`;
      return `${err.detail || '서버에서 오류가 났습니다. 잠시 후 다시 시도하세요.'} (오류 ${err.status})`;
    }
    return '서버에 연결하지 못했습니다. 네트워크와 서버 실행 상태를 확인하세요.';
  }

  // ------------------------------------------------------------------ 표시용 한국어화
  function clean(text) {
    if (!text) return '';
    let s = String(text);
    s = s.replace(/\s*\[kw:[^\]]*\]/g, '');
    s = s.replace(/^\(카드 규칙\)\s*/, '');
    s = s.replace(/'([a-z][a-z0-9_]*)'/g, (m, c) => (CLAIM_LABEL[c] ? `'${CLAIM_LABEL[c]}'` : m));
    // "적용 대상(cleanser_balm, cleanser_foam, …)" 같은 코드 목록 → 한국어
    s = s.replace(/\(([a-z][a-z0-9_]*(?:,\s*[a-z][a-z0-9_]*)+)\)/g, (m, list) =>
      `(${list.split(/,\s*/).map((t) => PTYPE[t] || CLAIM_LABEL[t] || t).join(', ')})`);
    s = s.replace(/\(expired_(\d{4})\)/g, '($1년 만료)');
    s = s.replace(/(시험 확인 필요:\s*)(.+)$/, (m, head, list) => head + list.split(/,\s*/).map((t) => TEST_LABEL[t.trim()] || t).join(', '));
    s = s.replace(/:\s*[A-Z]{2,6}_[A-Z0-9_]+\s+—\s+/, ': ');
    s = s.replace(/\b(vegan|halal|natrue) 기준/g, (m, c) => `${{ vegan: '비건', halal: '할랄', natrue: 'NATRUE' }[c]} 기준`);
    s = s.replace(/추정\(heuristic\)/g, '추정(성분명 단서)');
    return s.trim();
  }
  function cleanAction(a) {
    return clean(a)
      .replace(/^자사에게 준비 요청$/, '자사에서 준비')
      .replace(/^관공서에게 준비 요청$/, '관공서에 발급 신청')
      .replace(/^담당에게 준비 요청$/, '담당자에게 준비 요청');
  }
  // "EU Annex III ref 353 (규제원문_dl_cosing/annex_III.csv, 2023-10-12)" → 조문 + 갱신일, 파일은 title로
  function evidenceHTML(e) {
    const s = clean(e);
    const m = s.match(/^(.*?)\s*\(([^()]*\.(?:csv|pdf|xlsx?|json|txt|html?)),\s*([0-9]{4}-[0-9]{2}-[0-9]{2})\)\s*$/i);
    if (m) return `<span title="출처 파일: ${esc(m[2])}">${esc(m[1])}</span> <span class="muted">(목록 갱신 ${esc(m[3])})</span>`;
    return esc(s);
  }
  function docParts(message) {
    const body = clean(message).replace(/^(서류 필요|초안 자동 생성 가능):\s*/, '');
    const who = (body.match(/\s*\((?:작성|최종 작성·서명):\s*([^)]+)\)\s*$/) || [])[1] || '';
    const desc = body.replace(/\s*\((?:작성|최종 작성·서명):\s*[^)]+\)\s*$/, '');
    const short = desc.split(/:\s/)[0].replace(/\s*\(추정\)/g, '');
    return { desc, short, who };
  }
  const claimText = (codes) => (codes || []).map((c) => CLAIM_LABEL[c] || c);
  const pState = (s) => {
    s = s || '';
    if (s === 'user_input') return '직접 입력';
    if (/^on_market/.test(s)) return '판매 중';
    if (/^pilot/.test(s)) return '시제품';
    if (/develop|concept|plan/.test(s)) return '기획';
    return s || '미상';
  };
  const appText = (a) => (a === 'rinse_off' ? '씻어내는 제품' : '바르는 제품');
  function confInfo(c) {
    const v = typeof c === 'number' ? c : 1;
    const label = v >= 0.9 ? '높음' : v >= 0.6 ? '보통' : '낮음';
    return { label, pct: Math.round(v * 100), low: v < 0.6 };
  }

  // ------------------------------------------------------------------ 판정 결과 파생
  function gapType(code) {
    if (S.gapByCode && S.gapByCode[code]) return S.gapByCode[code]; // 서버(엔진)가 준 분류 우선
    for (const [k, g] of GAP_TYPES) {
      if (code.startsWith(k)) return k === 'ATTR_' && code.endsWith('_FAIL') ? '재처방' : g;
    }
    return '기타';
  }
  const colOf = (f) => GAP_COL_OF[gapType(f.code)] || 'docs';
  const isGap = (f) => f.level === 'fail' || f.level === 'cond';
  const certOf = (v) => S.certIndex[v.cert_id] || {};
  // AIStream 판정 모델(선택). 응답에 ml이 없거나 null·enabled=false여도 규칙 판정만으로 그린다
  const mlOf = (v) => (v && v.ml && typeof v.ml === 'object' ? v.ml : null);
  const pctOf = (p) => (typeof p === 'number' && isFinite(p) ? `${Math.round(p * 100)}%` : '');
  function mlState() {
    const m = S.result && S.result.ml;
    if (!m || typeof m !== 'object') return { kind: 'absent' };
    if (!m.enabled) return { kind: 'off' };
    if (!m.ok) return { kind: 'error', error: m.error || '' };
    return { kind: 'on', threshold: typeof m.threshold === 'number' ? m.threshold : null };
  }
  // 회사 단위 인증(메인비즈·이노비즈·벤처 등)은 제품 처방과 무관 — 요약 문장·개수·재처방 이유에서 뺀다
  const isCompany = (v) => v.kind === 'company_certification' || v.product_id === 'COMPANY';

  function verdictGaps(v) {
    const g = { reform: 0, docs: 0, local: 0, label: 0, test: 0 };
    let reformFail = false;
    if (v.gaps && typeof v.gaps === 'object' && Object.keys(v.gaps).length) {
      for (const [name, n] of Object.entries(v.gaps)) g[GAP_COL_OF[name] || 'docs'] += Number(n) || 0;
    } else {
      for (const f of v.findings || []) if (isGap(f)) g[colOf(f)] += 1;
    }
    for (const f of v.findings || []) if (f.level === 'fail') reformFail = true;
    return { g, reformFail };
  }

  function filterDef() { return FILTERS.find((f) => f.id === S.filter) || FILTERS[0]; }
  function visibleVerdicts() {
    if (!S.result) return [];
    const def = filterDef();
    return (S.result.verdicts || []).filter((v) => {
      const c = certOf(v);
      return def.test({ kind: v.kind || c.kind, jurisdiction: v.jurisdiction || c.jurisdiction, strategic_kr: c.strategic_kr });
    });
  }
  function counts(vs) {
    const c = { fail: 0, cond: 0, pass: 0, na: 0 };
    for (const v of vs) { const m = STATUS_BY[v.status]; if (m) c[m.key] += 1; }
    return c;
  }

  // 같은 코드가 반복되는 항목을 하나로 묶는다(할랄 원료 33건 등)
  const GROUPABLE = [
    { test: (c) => /^ATTR_.+_CHECK$/.test(c), subject: (m) => m.split(':')[0], title: (n) => `원료 ${n}종: 기원·인증 확인 필요` },
    { test: (c) => /^ATTR_.+_FAIL$/.test(c), subject: (m) => m.split(':')[0], title: (n, code) => `원료 ${n}종: ${ATTR_NAME[code.replace(/^ATTR_|_FAIL$/g, '')] || ''} 기준 불충족` },
    { test: (c) => c === 'ING_NOT_IN_INVENTORY', subject: (m) => (m.match(/미확인:\s*(.+?)\s+—/) || [])[1] || m, title: (n) => `기존 원료 목록에서 확인되지 않은 성분 ${n}종(표기 차이이거나 등록이 필요한 신원료)` },
    { test: (c) => c === 'ING_RESTRICTED_PCT_UNKNOWN', subject: (m) => (m.match(/제한 성분\s+(.+?):/) || [])[1] || m, title: (n) => `제한 성분 ${n}종: 함량을 몰라 한도 대조 필요` },
    { test: (c) => c === 'ALLERGEN_LABEL_RULE', subject: (m) => (m.match(/대상\s+(.+?)\s+—/) || [])[1] || m, title: (n) => `향료 알레르기 표시 대상 ${n}종(전성분에 표시됨)` },
    { test: (c) => c === 'CLAIM_OK', subject: (m) => (m.match(/'(.+?)'/) || [])[1] || m, title: (n, code, subs) => `표방 허용: ${subs.join(', ')}` },
  ];
  function groupFindings(list) {
    const out = [];
    const byKey = new Map();
    for (const f of list) {
      const rule = GROUPABLE.find((r) => r.test(f.code));
      if (!rule) { out.push({ type: 'one', f }); continue; }
      const key = `${f.code}|${f.action}`;
      let g = byKey.get(key);
      if (!g) { g = { type: 'group', rule, code: f.code, level: f.level, action: f.action, items: [] }; byKey.set(key, g); out.push(g); }
      g.items.push(f);
    }
    return out.map((x) => {
      if (x.type !== 'group' || x.items.length < 2) return x.type === 'group' ? { type: 'one', f: x.items[0] } : x;
      const msgs = x.items.map((f) => clean(f.message));
      const subs = msgs.map((m) => x.rule.subject(m));
      const evs = x.items.map((f) => f.evidence || '');
      const sameEv = evs.every((e) => e === evs[0]);
      return Object.assign(x, { title: x.rule.title(x.items.length, x.code, subs), subs, evs, sameEv });
    });
  }

  function reasonRank(f) {
    if (f.level === 'fail') return 0;
    const c = f.code;
    if (c === 'SILOXANE_SUNSET' || c === 'FORMULA_CONCEPT') return 1;
    if (c.startsWith('CLAIM_')) return 2;
    if (c.startsWith('ING_')) return 3;
    if (c.startsWith('ATTR_')) return 4;
    if (c.startsWith('ALLERGEN_')) return 5;
    if (c === 'HALAL_FACILITY' || c === 'PACKAGING_DATA' || c.startsWith('COMPANY_')) return 6;
    if (c === 'LOCAL_ENTITY_MISSING') return 7;
    if (c === 'TEST_MISSING' || c.startsWith('PROP65')) return 8;
    if (c === 'LABEL_LOCAL') return 9;
    if (c === 'DOC_MISSING') return 10;
    return 11;
  }
  function keyReason(v, common) {
    const fs = v.findings || [];
    if (v.status === ST.NA) {
      const f = fs.find((x) => x.level === 'na');
      return f ? clean(f.message) : '이 제품에는 적용되지 않습니다.';
    }
    const gaps = fs.filter(isGap);
    if (!gaps.length) return '보완할 항목이 없습니다.';
    const rank = (f) => (f.level === 'fail' ? 0 : 100) + (common && common.has(actionKey(f)) ? 50 : 0) + reasonRank(f);
    const top = groupFindings(gaps.slice().sort((a, b) => rank(a) - rank(b)))[0];
    if (top.type === 'one' && (top.f.code === 'DOC_MISSING' || top.f.code === 'DOC_DRAFTABLE')) {
      const n = gaps.filter((f) => f.code === top.f.code).length;
      const short = docParts(top.f.message).short;
      const head = top.f.code === 'DOC_MISSING' ? '필요 서류' : '자동 초안을 만들 수 있는 서류';
      return n > 1 ? `${head} ${n}건: ${short} 등` : `${head}: ${short}`;
    }
    return top.type === 'group' ? top.title : clean(top.f.message);
  }

  // "가장 먼저 할 일"과 행의 핵심 사유가 같은 기준으로 조치를 묶는다
  function actionKey(f) {
    if (f.code === 'DOC_MISSING') return `doc|${docParts(f.message).short}`;
    if (f.code === 'DOC_DRAFTABLE') return 'draftable';
    if (/^ATTR_.+_CHECK$/.test(f.code)) return 'attrcheck';
    if (f.level === 'fail') return `reform|${f.action || f.code}`;
    if (f.code === 'TEST_MISSING') return 'test';
    if (f.code === 'LOCAL_ENTITY_MISSING') return 'local';
    if (f.code === 'LABEL_LOCAL') return 'label';
    if (f.code === 'FORMULA_CONCEPT') return 'concept';
    return f.action ? `act|${cleanAction(f.action)}` : `msg|${clean(f.message)}`;
  }
  // 적용 인증의 절반 이상에 나오는 조치 — 요약의 "가장 먼저 할 일"이 이미 다루므로 행에서는 뒤로 미룬다
  function commonKeys(vs) {
    const app = vs.filter((v) => v.status !== ST.NA);
    const cnt = new Map();
    for (const v of app) {
      for (const k of new Set((v.findings || []).filter(isGap).map(actionKey))) cnt.set(k, (cnt.get(k) || 0) + 1);
    }
    const th = Math.max(3, Math.ceil(app.length * 0.5));
    return new Set(Array.from(cnt.entries()).filter(([, n]) => n >= th).map(([k]) => k));
  }

  // "세틸에틸헥사노에이트(Cetyl Ethylhexanoate)" → 국문명만
  const shortName = (s) => { const m = String(s).match(/^([^()]*[가-힣][^()]*)\(/); return m ? m[1].trim() : String(s); };

  function subjectOf(f) {
    const m = clean(f.message);
    if (/^ATTR_/.test(f.code)) return m.split(':')[0];
    const b = m.match(/^금지 성분:\s*(.+)$/) || m.match(/^제한 성분\s+(\S.+?)\s+[\d.]+%/) || m.match(/^([a-z0-9-]+)\(D\d\)/i);
    return b ? b[1] : m;
  }

  // 여러 인증에 공통인 조치 → 상위 3개
  function topActions(vs) {
    const map = new Map();
    for (const v of vs) {
      if (v.status === ST.NA) continue;
      for (const f of v.findings || []) {
        if (!isGap(f) || f.code === 'DOC_DRAFTABLE') continue; // 자동 초안은 '서류 초안'에서 안내한다
        const key = actionKey(f);
        let g = map.get(key);
        if (!g) { g = { key, col: colOf(f), fail: false, certs: new Map(), items: [] }; map.set(key, g); }
        if (f.level === 'fail') g.fail = true;
        g.certs.set(v.cert_id, v);
        g.items.push(f);
      }
    }
    const list = Array.from(map.values());
    list.sort((a, b) => (b.certs.size - a.certs.size) || (Number(b.fail) - Number(a.fail)) ||
      (COL_RANK[a.col] - COL_RANK[b.col]) || (b.items.length - a.items.length));
    return list.slice(0, 3).map(describeAction);
  }
  function uniq(arr) { return Array.from(new Set(arr.filter(Boolean))); }
  const marketOrder = (j) => { const i = JUR_ORDER.indexOf(j); return i < 0 ? 900 : i; };
  const byMarket = (a, b) => (marketOrder(a.jurisdiction) - marketOrder(b.jurisdiction)) || String(a.cert_id).localeCompare(String(b.cert_id));
  function describeAction(g) {
    const f0 = g.items[0];
    let title = cleanAction(f0.action) || clean(f0.message);
    let sub = '';
    let doc = null;
    let link = false;
    const k = g.key;
    if (k === 'local') { title = '현지 책임자 지정'; sub = '나라마다 현지 수입자·대리인(책임자)과 계약합니다.'; }
    else if (k === 'label') { title = '현지어 라벨 작성'; sub = '나라별 표시 언어와 표시사항을 맞춥니다.'; doc = 'label_draft'; }
    else if (k === 'test') {
      title = '부족한 시험 확인·의뢰';
      const tally = new Map();
      for (const f of g.items) {
        const list = (f.message.split(':')[1] || '').split(',').map((t) => t.trim()).filter(Boolean);
        for (const t of list) tally.set(t, (tally.get(t) || 0) + 1);
      }
      const names = Array.from(tally.entries()).sort((a, b) => b[1] - a[1]).map(([t]) => TEST_LABEL[t] || t);
      sub = `국내 성적서와 대조할 시험: ${names.slice(0, 4).join(', ')}${names.length > 4 ? ` 외 ${names.length - 4}종` : ''}`;
    } else if (k === 'attrcheck') {
      title = '원료 기원·인증 증명서 확보';
      const subs = uniq(g.items.map((f) => clean(f.message).split(':')[0]));
      sub = `원료사에서 받을 증명: ${subs.length}종(${subs.slice(0, 3).join(', ')}${subs.length > 3 ? ' 등' : ''})`;
    } else if (k === 'concept') { title = '처방 확정 후 다시 판정'; sub = '기획 단계라 성분·함량이 정해지지 않았습니다.'; }
    else if (k === 'draftable') {
      title = '자동 초안 서류 확인·서명';
      const names = uniq(g.items.map((f) => docParts(f.message).short));
      sub = `보유 자료로 초안을 만들 수 있는 서류 ${names.length}종(${names.slice(0, 2).join(', ')}${names.length > 2 ? ' 등' : ''})은 담당자가 확인하고 서명합니다.`;
      link = true;
    }
    else if (k.startsWith('doc|')) {
      const p = docParts(f0.message);
      title = `${p.short} 준비`;
      sub = p.who ? `작성: ${p.who}` : '';
    } else if (k.startsWith('reform|')) {
      const subs = uniq(g.items.map(subjectOf));
      sub = `대상: ${subs.slice(0, 3).join(', ')}${subs.length > 3 ? ` 외 ${subs.length - 3}종` : ''}`;
    } else if (g.items.length) {
      const m = clean(f0.message);
      if (m !== title) sub = m;
    }
    const vs = Array.from(g.certs.values());
    let where;
    if (vs.length <= 2) where = vs.map((v) => v.cert_name).join(', ');
    else {
      const js = uniq(vs.slice().sort(byMarket).map((v) => jurName(v.jurisdiction)));
      where = `${js.slice(0, 4).join(', ')}${js.length > 4 ? ` 외 ${js.length - 4}곳` : ''}`;
    }
    return { title, sub, where, n: vs.length, col: g.col, fail: g.fail, doc, link };
  }

  function summarySentence(c, vs) {
    const n = c.fail + c.cond + c.pass;
    const out = { main: '', sub: [], fail: '' };
    if (!n) {
      out.main = '이 제품에 적용되는 인증이 없습니다.';
      if (c.na) out.sub.push(`대상 인증 ${c.na}개 모두 이 제품 유형·표방에는 적용되지 않습니다.`);
      return out;
    }
    if (!c.fail && !c.cond) out.main = `적용되는 인증 ${n}개 모두 지금 상태로 통과할 수 있습니다.`;
    else if (!c.fail) out.main = `적용되는 인증 ${n}개 모두 재처방 없이 통과할 수 있습니다.`;
    else if (c.fail === n) out.main = `적용되는 인증 ${n}개 모두 재처방해야 통과합니다.`;
    else out.main = `적용되는 인증 ${n}개 중 ${c.cond + c.pass}개는 재처방 없이 통과할 수 있고, ${c.fail}개는 재처방이 필요합니다.`;

    if (c.cond) {
      out.sub.push(c.pass
        ? `${c.pass}개는 지금 바로 통과하고, ${c.cond}개는 서류·현지 책임자·문구·시험을 보완하면 통과합니다.`
        : `지금 바로 통과하는 인증은 없고, ${c.fail ? `${c.cond}개는` : `${c.cond}개 모두`} 서류·현지 책임자·문구·시험을 보완해야 합니다.`);
    } else if (c.pass && c.fail) {
      out.sub.push(`${c.pass}개는 지금 바로 통과합니다.`);
    }
    if (c.fail) {
      const failVs = vs.filter((v) => v.status === ST.FAIL).sort(byMarket);
      const ings = uniq([].concat(...failVs.map((v) => (v.findings || []).filter((f) => f.level === 'fail').map((f) => shortName(subjectOf(f))))));
      const names = failVs.map((v) => v.cert_name);
      out.fail = `재처방이 필요한 인증 ${failVs.length}개: ${names.slice(0, 2).join(', ')}${names.length > 2 ? ` 외 ${names.length - 2}개` : ''}.` +
        (ings.length ? ` 걸리는 원료: ${ings.slice(0, 3).join(', ')}${ings.length > 3 ? ` 외 ${ings.length - 3}종` : ''}.` : '');
    }
    if (c.na) out.sub.push(`${c.na}개는 이 제품에 적용되지 않습니다.`);
    return out;
  }

  // ------------------------------------------------------------------ 렌더: 공통 조각
  function badge(status, small) {
    const m = STATUS_BY[status] || STATUS_BY[ST.NA];
    return `<span class="badge badge--${m.key}${small ? ' badge--sm' : ''}">${icon(m.icon)}${esc(status)}</span>`;
  }
  function catChip(col) {
    const c = GAP_COLS.find((x) => x.id === col) || GAP_COLS[1];
    return `<span class="cat${col === 'reform' ? ' cat--reform' : ''}">${icon(c.icon)}${esc(c.label)}</span>`;
  }
  function legendHTML(c) {
    return `<ul class="legend" role="list" aria-label="판정 등급">${STATUS_LIST.map((m) => {
      const n = c ? c[m.key] : null;
      const count = n == null ? '–' : String(n);
      return `<li class="legend__cell legend__cell--${m.key}">
        <p class="legend__label">${icon(m.icon)}${esc(m.s)}</p>
        <p class="legend__count${!n ? ' legend__count--zero' : ''}">${esc(count)}${n == null ? '' : '<span class="sr-only">개</span>'}</p>
        <p class="legend__def">${esc(m.def)}</p>
      </li>`;
    }).join('')}</ul>`;
  }

  // ------------------------------------------------------------------ 렌더: 작업대
  function renderDemoList() {
    const list = $('#demo-list');
    const prods = (S.demo && S.demo.products) || [];
    list.setAttribute('aria-busy', 'false');
    if (!prods.length) {
      list.innerHTML = '<li class="state state--quiet">데모 제품이 없습니다.</li>';
      return;
    }
    list.innerHTML = prods.map((p) => {
      const ing = (p.ingredients || []).length;
      const formula = FORMULA[p.formula_known] || '';
      const claims = claimText(uniq([].concat(p.functional_kr || [], p.claims || [])));
      const type = PTYPE[p.product_type] || '';
      return `<li><button type="button" class="demo" data-demo="${esc(p.id)}" aria-pressed="${S.demoId === p.id && S.source === 'demo'}">
        <span class="demo__head"><span class="demo__id">${esc(p.id)}</span><span class="demo__name">${esc(p.name_kr)}</span></span>
        <span class="demo__side">${icon('i-loader', 'btn__spin')}<span class="tag tag--state">${esc(pState(p.status))}</span></span>
        <span class="demo__meta">${esc([appText(p.application), type, `성분 ${ing}종${formula ? `(${formula})` : ''}`].filter(Boolean).join(', '))}</span>
        <span class="demo__claims">표방: ${esc(claims.slice(0, 3).join(', ') || '없음')}${claims.length > 3 ? ` 외 ${claims.length - 3}` : ''}</span>
      </button></li>`;
    }).join('');
  }

  function renderCompany() {
    const c = S.company || {};
    const role = String(c.role_kr || '').replace(/\(가상\)/g, '').trim();
    $('#company-line').textContent = c.name ? `회사: ${c.name}${role ? `, ${role}` : ''}` : '회사 정보 없음';
  }

  function renderFilter() {
    const wrap = $('#filter-chips');
    wrap.innerHTML = FILTERS.map((f) => {
      const n = S.certs.filter((c) => f.test(c)).length;
      return `<label class="chip-radio"><input type="radio" name="filter" value="${f.id}"${S.filter === f.id ? ' checked' : ''}>
        <span class="chip-radio__face">${icon('i-check', 'ic--sm')}${esc(f.label)} <span class="chip-radio__n">${n}</span></span></label>`;
    }).join('');
  }

  function renderManualOptions() {
    $('#m-claims').innerHTML = CLAIM_OPTS.map(([v, l]) =>
      `<label class="opt"><input type="checkbox" name="m-claim" value="${v}"><span>${esc(l)}</span></label>`).join('');
    $('#m-docs').innerHTML = DOC_OPTS.map(([v, l]) =>
      `<label class="opt"><input type="checkbox" name="m-doc" value="${v}"><span>${esc(l)}</span></label>`).join('') +
      MFR_OPTS.map(([v, l]) =>
        `<label class="opt"><input type="checkbox" name="m-mfr" value="${v}"><span>${esc(l)}</span></label>`).join('') +
      '<p class="extras" id="m-extras" hidden></p>';
    const sel = $('#m-fill');
    for (const p of (S.demo && S.demo.products) || []) {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = `${p.id} ${p.name_kr}`;
      sel.appendChild(o);
    }
  }

  // ------------------------------------------------------------------ 렌더: 판정서
  function resetSummaryTitle() {
    const t = $('#summary-title');
    t.textContent = '판정 요약';
    t.classList.remove('report__title');
  }
  function renderEmpty() {
    resetSummaryTitle();
    $('#summary-body').innerHTML = `<p class="empty-lede">데모 제품을 고르거나 직접 입력하면, 인증·등록마다 아래 네 가지 중 하나로 예비 판정합니다.</p>${legendHTML(null)}`;
    $('#table-body').innerHTML = '<p class="muted">판정하면 관할(국가)별 표가 여기에 나옵니다.</p>';
  }

  // 함량이 없어 한도 대조를 못 한 제한 성분. 추측(ML) 대신 사용자에게 함량을 물어 판정을 확정한다
  const PCT_ASK_RE = /제한 성분\s+(.+?):/;
  function pctAskList(vs) {
    const by = new Map();
    for (const v of vs) {
      for (const f of v.findings || []) {
        if (f.code !== 'ING_RESTRICTED_PCT_UNKNOWN') continue;
        const name = ((f.message || '').match(PCT_ASK_RE) || [])[1];
        if (!name) continue;
        if (!by.has(name)) by.set(name, new Set());
        by.get(name).add(v.cert_name);
      }
    }
    return Array.from(by, ([name, certs]) => ({ name, certs: Array.from(certs) })).sort((a, b) => b.certs.length - a.certs.length);
  }
  function pctAskHTML(vs) {
    const list = pctAskList(vs);
    if (!list.length) return '';
    const shown = list.slice(0, 6);
    return `<section class="pctask" aria-labelledby="pctask-title"><h3 class="sub-title" id="pctask-title">함량을 넣으면 판정이 확정되는 성분 ${list.length}종</h3>
      <p class="pctask__text">한도가 있는 성분인데 함량이 없어 한도를 넘는지 알 수 없습니다. 함량을 넣고 다시 판정하면 이 성분 때문에 생긴 ‘조건부’가 통과 또는 불가로 바뀝니다.</p>
      <ul class="pctask__list" role="list">${shown.map((x) => `<li><span class="pctask__name">${esc(x.name)}</span>
        <span class="pctask__certs">인증 ${x.certs.length}개: ${esc(x.certs.slice(0, 3).join(', '))}${x.certs.length > 3 ? ' 외' : ''}</span></li>`).join('')}</ul>
      ${list.length > shown.length ? `<p class="pctask__more">외 ${list.length - shown.length}종</p>` : ''}
      <div class="pctask__act"><button type="button" class="btn btn--secondary btn--sm" data-pct-ask="${esc(shown[0].name)}">${icon('i-flask', 'ic--sm')}함량 입력하기</button></div>
    </section>`;
  }
  // 입력 화면으로 옮겨 첫 성분 줄 끝에 커서를 둔다(데모면 데모 내용을 직접 입력 칸에 채운 뒤)
  function goPctInput(name) {
    if (S.source === 'demo' && S.demoId) {
      const sel = $('#m-fill');
      if (sel) sel.value = S.demoId;
      fillFromDemo(S.demoId);
    }
    selectTab(document.getElementById('tab-manual'));
    const ta = $('#m-ing');
    const lines = ta.value.split('\n');
    const key = name.toLowerCase();
    let pos = ta.value.length;
    let acc = 0;
    for (const line of lines) {
      if (line.toLowerCase().includes(key)) { pos = acc + line.length; break; }
      acc += line.length + 1;
    }
    ta.focus();
    ta.setSelectionRange(pos, pos);
    ta.scrollIntoView({ block: 'center' });
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-pct-ask]');
    if (b) goPctInput(b.dataset.pctAsk);
  });

  function renderSummary() {
    const p = S.product;
    const all = visibleVerdicts();
    const vs = all.filter((v) => !isCompany(v));
    const cvs = all.filter(isCompany);
    const c = counts(vs);
    const sen = summarySentence(c, vs);
    const ing = (p.ingredients || []).length;
    const formula = FORMULA[p.formula_known] || '';
    const fdef = filterDef();
    const title = $('#summary-title');
    title.innerHTML = `<span class="sr-only">판정 요약: </span>${esc(p.name_kr || '제품')}`;
    title.classList.add('report__title');

    const notes = [];
    if (vs.some((v) => (v.findings || []).some((f) => f.code === 'FORMULA_CONCEPT'))) {
      notes.push('처방이 정해지지 않은 기획 단계 제품이라 판정 신뢰도가 낮습니다. 처방을 확정한 뒤 다시 판정하세요.');
    }
    const lowN = vs.filter((v) => v.status !== ST.NA && confInfo(v.confidence).label !== '높음').length;
    if (lowN && !notes.length) notes.push(`${lowN}개 인증은 성분 규정 데이터가 부분적이라 신뢰도가 보통 이하입니다. 펼치면 이유를 볼 수 있습니다.`);

    const strategic = vs.filter((v) => certOf(v).strategic_kr).sort(byMarket);
    const general = vs.filter((v) => !certOf(v).strategic_kr && /일반/.test(certOf(v).support_rate || ''));
    const todos = topActions(vs);

    const meta = [
      ['처방 상태', pState(p.status)],
      ['사용 방식', appText(p.application)],
      PTYPE[p.product_type] && p.product_type !== 'cosmetic' ? ['제품 유형', PTYPE[p.product_type]] : null,
      ['전성분', `${ing}종${formula ? `, ${formula}` : ''}`],
      ['판정 대상', `${fdef.label} ${vs.length}개${cvs.length ? `, 회사 단위 ${cvs.length}개` : ''}`],
    ].filter(Boolean);

    let html = `<div class="report__body">
      <p class="report__tags"><span class="tag tag--brand">${icon('i-info', 'ic--sm')}예비 판정</span><span>기준일 ${esc((S.result && S.result.eval_date) || today())}</span></p>
      <dl class="report__meta">${meta.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`;
    if (!all.length) {
      html += `<div class="state state--quiet">${icon('i-info')}<div><p class="state__title">이 조건에 맞는 인증이 없습니다.</p>
        <p class="state__text">‘판정 대상’을 전체로 바꾸면 모든 인증의 판정을 볼 수 있습니다. 이 범위의 인증 요건 카드는 아직 준비 중일 수 있습니다.</p></div></div>`;
      html += legendHTML(c);
    } else {
      html += `<p class="verdict">${esc(sen.main)}</p>`;
      if (sen.sub.length) html += `<p class="verdict-sub">${esc(sen.sub.join(' '))}</p>`;
      if (sen.fail) html += `<p class="note note--fail">${icon('i-fail', 'ic--sm')}<span>${esc(sen.fail)}</span></p>`;
      html += mlAlertHTML(vs);
      for (const n of notes) html += `<p class="note">${icon('i-info', 'ic--sm')}<span>${esc(n)}</span></p>`;
      html += mlStatusHTML(vs);
      html += nameConvHTML();
      html += legendHTML(c);
      if (todos.length) {
        html += `<section class="todo" aria-labelledby="todo-title"><h3 class="sub-title" id="todo-title">가장 먼저 할 일</h3>
          <ol class="todo__list" role="list">${todos.map((t, i) => `<li class="todo__item">
            <span class="todo__n" aria-hidden="true">${i + 1}</span>
            <div>
              <div class="todo__head"><p class="todo__title">${esc(t.title)}</p>${catChip(t.col)}</div>
              ${t.sub ? `<p class="todo__sub">${esc(t.sub)}</p>` : ''}
              <p class="todo__certs"><strong>인증 ${t.n}개${t.n > 1 ? ' 공통' : ''}</strong>: ${esc(t.where)}</p>
              ${t.doc && S.docTypes instanceof Set && S.docTypes.has(t.doc) ? `<div class="todo__act">${docButton(t.doc, '초안 내려받기', 'btn--quiet btn--sm')}</div>` : ''}
              ${t.link ? '<div class="todo__act"><a class="btn btn--quiet btn--sm" href="#docs">서류 초안 보기</a></div>' : ''}
            </div></li>`).join('')}</ol></section>`;
      }
      html += pctAskHTML(vs);
      if (strategic.length) {
        html += `<section class="support" aria-labelledby="support-title">${icon('i-landmark', 'ic--lg support__icon')}<div>
          <h3 class="support__title" id="support-title">중기부 해외규격인증 지원 대상(비용 50~70%)</h3>
          <p class="support__text">전략인증 ${strategic.length}개는 인증 비용의 50~70%(최대 1억 원)를 지원받을 수 있습니다.${general.length ? ` 일반 지원 목록(583종)에 있는 인증도 ${general.length}개 있습니다.` : ''}</p>
          <ul class="support__list" role="list">${strategic.map((v) => `<li>${badge(v.status, true)}${esc(v.cert_name)}</li>`).join('')}</ul>
          ${S.docTypes instanceof Set && S.docTypes.has('support_program') ? `<div class="support__act">${docButton('support_program', '지원사업 신청 메모 내려받기', 'btn--secondary btn--sm')}</div>` : ''}
        </div></section>`;
      }
      if (cvs.length) html += companyHTML(cvs);
    }
    html += '</div>';
    $('#summary-body').innerHTML = html;
  }

  function nameConvHTML() {
    const n = S.result && S.result.ingredient_names;
    if (!n || (!(n.converted || []).length && !(n.unmatched || []).length)) return '';
    const conv = (n.converted || []).length;
    const miss = n.unmatched || [];
    let text = `한글 성분명 ${conv}종을 식약처 원료성분 사전으로 영문 INCI로 바꿔 대조했습니다.`;
    if (miss.length) text += ` 사전에서 찾지 못한 ${miss.length}종(${miss.slice(0, 5).join(', ')}${miss.length > 5 ? ' 등' : ''})은 영문 INCI로 다시 적어 주세요.`;
    return `<p class="note">${icon(miss.length ? 'i-cond' : 'i-info', 'ic--sm')}<span>${esc(text)}</span></p>`;
  }
  function mlStatusHTML(vs) {
    const st = mlState();
    if (st.kind === 'absent') return '';
    let text;
    if (st.kind === 'off') text = 'AIStream 판정 모델이 연결되지 않아 규칙 판정만 보여 줍니다.';
    else if (st.kind === 'error') text = 'AIStream 판정 모델이 응답하지 않아 이번에는 규칙 판정만 보여 줍니다.';
    else {
      const judged = vs.filter((v) => mlOf(v));
      const agree = judged.filter((v) => mlOf(v).agree).length;
      text = judged.length
        ? `AIStream 판정 모델이 함께 검토했습니다. ${judged.length}개 중 ${agree}개가 규칙 판정과 같습니다. 행마다 AI 판정을 작게 표시합니다.`
        : 'AIStream 판정 모델이 연결되어 있습니다. 이 범위에는 모델이 검토한 인증이 없습니다.';
    }
    const title = st.kind === 'error' && st.error ? ` title="${esc(st.error)}"` : '';
    return `<p class="note note--ml"${title}>${icon('i-cpu', 'ic--sm')}<span>${esc(text)}</span></p>`;
  }
  function mlAlertHTML(vs) {
    if (mlState().kind !== 'on') return '';
    const alerts = vs.filter((v) => mlOf(v) && mlOf(v).hidden_fail_alert).sort(byMarket);
    if (!alerts.length) return '';
    const names = alerts.map((v) => v.cert_name);
    return `<div class="mlalert" role="note">${icon('i-alert', 'ic--sm')}<div>
      <p class="mlalert__title">불가 가능성 경보 ${alerts.length}건: ${esc(names.slice(0, 2).join(', '))}${names.length > 2 ? ` 외 ${names.length - 2}개` : ''}</p>
      <p class="mlalert__text">규칙으로는 불가가 아니지만, 입력한 자료가 부족한 상태라 AI 모델은 실제로는 불가일 가능성이 높다고 봤습니다. 해당 인증의 원료 규격서와 함량 자료를 다시 확인하세요.</p>
    </div></div>`;
  }
  // 행의 작은 AI 판정 표시: 규칙과 같으면 흐리게, 다르면 등급 색·확률과 함께
  function mlGradeHTML(v) {
    const m = mlOf(v);
    if (!m) return '';
    const meta = STATUS_BY[m.status];
    const p = !m.agree && m.proba && typeof m.proba[m.label] === 'number' ? pctOf(m.proba[m.label]) : '';
    const mod = m.agree ? 'agree' : (meta ? meta.key : 'na');
    return `<span class="mlgrade mlgrade--${mod}"><span class="mlgrade__k" aria-hidden="true">AI</span><span class="sr-only">AI 모델 판정 </span>${meta ? icon(meta.icon, 'ic--xs') : ''}${esc(m.status || m.label || '')}${p ? ` ${p}` : ''}${m.agree ? '<span class="sr-only">, 규칙 판정과 같음</span>' : ''}</span>`;
  }
  // 상세의 AI 판정 줄(meta)과, 숨은 불가 경보가 있으면 맨 위 경보 블록(alert)
  function mlDetailHTML(v) {
    const m = mlOf(v);
    if (!m) return null;
    const label = { FAIL: ST.FAIL, COND: ST.COND, PASS: ST.PASS, NA: ST.NA };
    const dist = m.proba ? ['FAIL', 'COND', 'PASS', 'NA'].filter((k) => typeof m.proba[k] === 'number')
      .map((k) => `${label[k]} ${pctOf(m.proba[k])}`).join(', ') : '';
    const meta = `<dt>AI 모델 판정</dt><dd>${esc(m.status || m.label || '-')}${m.agree ? ' (규칙 판정과 같음)' : ' (규칙 판정과 다름)'}${dist ? `<span class="muted"> 확률: ${esc(dist)}</span>` : ''}</dd>`;
    if (!m.hidden_fail_alert) return { meta, alert: '' };
    const th = mlState().threshold;
    const fp = pctOf(m.fail_proba);
    const how = fp ? `${fp}로` : '높게';
    const alert = `<div class="mlalert" role="note">${icon('i-alert', 'ic--sm')}<div>
      <p class="mlalert__title">불가 가능성 경보</p>
      <p class="mlalert__text">규칙 판정은 ${esc(m.rule_status || v.status)}이지만, AI 모델은 불가일 확률을 ${esc(how)} 봤습니다${th != null ? `(경보 기준 ${esc(pctOf(th))} 이상)` : ''}. 입력한 원료·함량 자료가 부족하면 실제로는 불가일 수 있습니다. 원료 규격서(COA)와 함량 자료를 다시 확인한 뒤 다시 판정하세요.</p>
    </div></div>`;
    return { meta, alert };
  }

  function companyHTML(cvs) {
    const items = cvs.slice().sort((a, b) => RANK[a.status] - RANK[b.status]).map((v) => {
      const f = (v.findings || []).filter(isGap).sort((a, b) => reasonRank(a) - reasonRank(b))[0];
      const why = f ? clean(f.message) : '요건을 충족합니다.';
      const act = f && f.action ? cleanAction(f.action) : '';
      return `<li class="corp__item">${badge(v.status, true)}<div><p class="corp__name">${esc(v.cert_name)}</p>
        <p class="corp__why">${esc(why)}${act ? `<span class="muted"> 해야 할 일: ${esc(act)}</span>` : ''}</p></div></li>`;
    }).join('');
    return `<section class="corp" aria-labelledby="company-title"><h3 class="sub-title" id="company-title">회사 단위 인증</h3>
      <p class="hint">제품과 관계없이 회사 요건(재무·업력·인력 등)으로 판정합니다. 여기서 불가는 회사 요건을 먼저 갖춰야 신청할 수 있다는 뜻입니다.</p>
      <ul class="corp__list" role="list">${items}</ul></section>`;
  }

  function gapCells(v) {
    const { g, reformFail } = verdictGaps(v);
    const on = [];
    const cells = GAP_COLS.map((col) => {
      const n = g[col.id];
      if (!n) return `<span class="gap gap--off" aria-hidden="true"></span>`;
      const mod = col.id === 'reform' ? (reformFail ? ' gap--reform' : ' gap--sunset') : '';
      on.push(`${col.label} ${n}건`);
      return `<span class="gap${mod}" aria-hidden="true"><span class="gap__mark"></span><span class="gap__label">${esc(col.label)}</span>${n > 1 ? `<span>${n}</span>` : ''}</span>`;
    }).join('');
    return { cells, any: on.length > 0, sr: on.length ? `보완: ${on.join(', ')}` : '보완할 항목 없음' };
  }

  function rowHTML(v, common) {
    const id = rowId(v.cert_id);
    const c = certOf(v);
    const conf = confInfo(v.confidence);
    const gaps = gapCells(v);
    const open = S.expanded.has(v.cert_id);
    return `<li class="vrow${open ? ' is-open' : ''}" data-status="${STATUS_BY[v.status] ? STATUS_BY[v.status].key : 'na'}">
      <button type="button" class="vrow__btn" id="b-${id}" data-cert="${esc(v.cert_id)}" aria-expanded="${open}" aria-controls="d-${id}">
        <span class="vrow__badge">${badge(v.status)}${mlGradeHTML(v)}</span>
        <span class="vrow__main">
          <span class="vrow__name">${esc(v.cert_name)}${c.strategic_kr ? '<span class="tag tag--brand">전략인증</span>' : ''}${mlOf(v) && mlOf(v).hidden_fail_alert ? `<span class="tag tag--alert">${icon('i-alert', 'ic--xs')}불가 가능성</span>` : ''}</span>
          <span class="vrow__reason">${esc(keyReason(v, common))}</span>
        </span>
        <span class="vrow__gaps${gaps.any ? '' : ' vrow__gaps--none'}">${gaps.cells}<span class="sr-only">${esc(gaps.sr)}</span></span>
        <span class="vrow__conf${conf.low ? ' vrow__conf--low' : ''}"><span class="conf-prefix">신뢰도 </span>${esc(conf.label)}</span>
        <span class="vrow__chev">${icon('i-chevron')}</span>
      </button>
      <div class="vrow__detail" id="d-${id}" role="region" aria-labelledby="b-${id}"${open ? ' data-ready="1"' : ' hidden'}>${open ? detailHTML(v) : ''}</div>
    </li>`;
  }

  function findingHTML(item) {
    if (item.type === 'group') {
      const lvl = item.level;
      const ic = lvl === 'fail' ? 'i-fail' : lvl === 'cond' ? 'i-cond' : 'i-info';
      const evCommon = item.sameEv && item.evs[0] ? `<dt>근거</dt><dd>${evidenceHTML(item.evs[0])}</dd>` : '';
      const members = item.subs.map((s, i) => `<li>${esc(s)}${!item.sameEv && item.evs[i] ? ` <span class="muted">(${evidenceHTML(item.evs[i])})</span>` : ''}</li>`).join('');
      const gtg = isGap({ level: lvl }) ? gapType(item.code) : '';
      const tag = gtg && !PLAIN_GAPS.has(gtg) ? `<span class="tag">${esc(gtg)}</span>` : '';
      return `<li class="finding finding--${lvl}">${icon(ic, 'ic--sm')}<div>
        <p class="finding__msg">${esc(item.title)}${tag}</p>
        <details class="more members"><summary>${icon('i-chevron', 'ic--sm')}대상 ${item.subs.length}종 보기</summary><ul role="list">${members}</ul></details>
        ${evCommon || item.action ? `<dl class="kv">${evCommon}${item.action ? `<dt>해야 할 일</dt><dd>${esc(cleanAction(item.action))}</dd>` : ''}</dl>` : ''}
      </div></li>`;
    }
    const f = item.f;
    const ic = f.level === 'fail' ? 'i-fail' : f.level === 'cond' ? 'i-cond' : f.level === 'na' ? 'i-na' : 'i-info';
    const gt = isGap(f) ? gapType(f.code) : '';
    const showTag = gt && !PLAIN_GAPS.has(gt);
    const kv = [
      f.evidence ? `<dt>근거</dt><dd>${evidenceHTML(f.evidence)}</dd>` : '',
      f.action ? `<dt>해야 할 일</dt><dd>${esc(cleanAction(f.action))}</dd>` : '',
    ].join('');
    return `<li class="finding finding--${f.level}">${icon(ic, 'ic--sm')}<div>
      <p class="finding__msg">${esc(clean(f.message))}${showTag ? `<span class="tag">${esc(gt)}</span>` : ''}</p>
      ${kv ? `<dl class="kv">${kv}</dl>` : ''}
    </div></li>`;
  }

  function relatedDocs(v) {
    const out = [];
    const id = v.cert_id.toUpperCase();
    if (id.includes('CPNP')) out.push('cpnp_sheet');
    if (id.includes('MOCRA')) out.push('mocra_sheet');
    if ((v.findings || []).some((f) => f.code === 'LABEL_LOCAL' || (isGap(f) && f.code.startsWith('CLAIM_')))) out.push('label_draft');
    if (v.status === ST.FAIL || v.status === ST.COND) out.push('gap_checklist');
    return out.slice(0, 3);
  }

  // AgentStream LLM+RAG 판정 설명(선택). 판정 표시와 따로 불러와 판정 속도를 늦추지 않는다. 등급은 규칙 엔진 결과 그대로
  const llmOn = () => !!(S.health && S.health.llm_model);
  function explainSlotHTML(v) {
    if (!llmOn() || isCompany(v)) return '';
    return `<section class="aiexp" data-explain="${esc(v.cert_id)}" aria-label="AI 판정 설명" aria-live="polite">${explainBodyHTML(S.explain[v.cert_id])}</section>`;
  }
  function explainTextHTML(text) {
    const out = [];
    let list = [];
    const flush = () => { if (list.length) out.push(`<ul class="aiexp__list" role="list">${list.join('')}</ul>`); list = []; };
    for (const raw of String(text || '').split(/\n+/)) {
      const line = raw.trim().replace(/^\*\*(.+?)\*\*/, '$1');
      if (!line) continue;
      const m = line.match(/^[-*•]\s+(.*)$/);
      if (m) list.push(`<li>${esc(m[1])}</li>`);
      else { flush(); out.push(`<p>${esc(line)}</p>`); }
    }
    flush();
    return out.join('');
  }
  function explainBodyHTML(st) {
    const head = `<h4 class="aiexp__title">${icon('i-cpu', 'ic--sm')}AI 판정 설명 <span class="aiexp__by">AgentStream · qwen3.5-122b + 지식베이스</span></h4>`;
    if (!st || st.loading) {
      return `${head}<p class="aiexp__state">${icon('i-loader', 'ic--sm aiexp__spin')}근거 문서를 찾아 설명을 만드는 중입니다. 보통 10초 안팎 걸립니다.</p>`;
    }
    const d = st.data || {};
    const src = (d.sources || []).map((s) => `<li><span class="aiexp__n">근거 ${esc(s.n)}</span> ${s.url
      ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.title || s.url)}</a>`
      : esc(s.title)} <span class="muted">${esc(s.kind || '')}</span></li>`).join('');
    const srcHTML = src ? `<details class="more aiexp__src"><summary>${icon('i-chevron', 'ic--sm')}근거 목록 ${(d.sources || []).length}건</summary>
      <div class="more__body"><ol class="flist" role="list">${src}</ol></div></details>` : '';
    if (st.error || !d.ok) {
      const busy = /RateLimit|LLM_RATE_LIMITED|HTTP 429|HTTP 503/.test(d.error || '');
      return `${head}<p class="aiexp__state">${icon('i-info', 'ic--sm')}${busy ? 'AI 모델에 요청이 몰려 지금은 설명을 만들지 못했습니다. 잠시 뒤 다시 불러오세요.' : 'AI 설명을 지금 불러오지 못했습니다.'} 판정과 근거는 위 내용 그대로 유효합니다.</p>
        <button type="button" class="btn btn--secondary btn--sm" data-explain-retry="${esc(d.cert_id || st.certId || '')}">${icon('i-refresh', 'ic--sm')}다시 불러오기</button>${srcHTML}`;
    }
    // 지식베이스 조회 결과: 이 인증 카드 조각만 '파일: 절' 묶음으로, 다른 카드 조각은 개수만(rag_target·rag_other가 없으면 옛 응답 모양)
    const other = d.rag_other ? ` · 다른 인증 카드 조각 ${d.rag_other}건은 제외` : '';
    const rag = d.tool_failed ? '<p class="aiexp__rag muted">지식베이스 문서 조회가 실패해 판정 사유만으로 설명했습니다.</p>'
      : d.rag_target === 0 ? `<p class="aiexp__rag muted">지식베이스에서 이 인증 카드를 찾지 못해 판정 사유만으로 설명했습니다${esc(other)}.</p>`
      : (d.rag_sources || []).length ? `<p class="aiexp__rag muted">지식베이스에서 찾은 이 인증 카드: ${esc(d.rag_sources.join(' / '))}${esc(other)}</p>` : '';
    const unv = (d.unverified || []).length
      ? `<p class="aiexp__check">${icon('i-alert', 'ic--sm')}<span>설명 속 날짜·비율 중 판정 사유와 지식베이스에서 확인되지 않은 값: ${esc(d.unverified.join(', '))}. 원문 확인이 필요합니다.</span></p>` : '';
    return `${head}<div class="aiexp__text">${explainTextHTML(d.text)}</div>${unv}${rag}${srcHTML}
      <p class="aiexp__notice">${icon('i-info', 'ic--xs')}${esc(d.notice || '참고용 설명이며 공식 인증·심사가 아닙니다.')}</p>`;
  }
  function renderExplain(certId) {
    const slot = document.querySelector(`.aiexp[data-explain="${CSS.escape(certId)}"]`);
    if (slot) slot.innerHTML = explainBodyHTML(S.explain[certId]);
  }
  async function loadExplain(certId, force) {
    if (!llmOn() || !S.product) return;
    const cur = S.explain[certId];
    if (cur && !force && (cur.loading || (cur.data && cur.data.ok))) return;
    const gen = S.explainGen;
    S.explain[certId] = { loading: true, certId };
    renderExplain(certId);
    let st;
    try {
      const res = await postJSON('api/explain', { product: S.product, company: S.company, cert_id: certId },
        { signal: AbortSignal.timeout(90000) }); // 연결이 조용히 끊겨도 '만드는 중'에 멈추지 않고 재시도 버튼으로
      const data = await res.json();
      st = data && data.enabled === false ? null : { data, certId };
    } catch (err) {
      st = { error: true, certId };
    }
    if (gen !== S.explainGen) return; // 그사이 다른 제품을 판정했으면 버린다
    if (st) S.explain[certId] = st; else delete S.explain[certId];
    const slot = document.querySelector(`.aiexp[data-explain="${CSS.escape(certId)}"]`);
    if (!st && slot) slot.remove(); else renderExplain(certId);
  }

  function detailHTML(v) {
    const c = certOf(v);
    const conf = confInfo(v.confidence);
    const fs = v.findings || [];
    const confWhy = uniq(fs.filter((f) => CONF_CODES.has(f.code)).map((f) => clean(f.message)));
    const ml = mlDetailHTML(v);
    let html = `${ml ? ml.alert : ''}<dl class="dmeta">
      <dt>관할</dt><dd>${esc(jurName(v.jurisdiction))} <span class="muted">${esc(v.jurisdiction)}</span></dd>
      <dt>종류</dt><dd>${esc(KIND[v.kind] || v.kind || '-')}</dd>
      ${c.name_en ? `<dt>영문명</dt><dd>${esc(c.name_en)}</dd>` : ''}
      <dt>신뢰도</dt><dd>${esc(conf.label)} ${conf.pct}%${confWhy.length ? `. 낮춘 이유: ${esc(confWhy.join(' / '))}` : ''}</dd>
      ${ml ? ml.meta : ''}
      ${c.support_rate ? `<dt>중기부 지원</dt><dd>${esc(c.support_rate)}</dd>` : ''}
      ${typeof c.export_share_2025 === 'number' ? `<dt>수출 비중</dt><dd>한국 화장품 수출(2025)의 ${esc((c.export_share_2025 * 100).toFixed(1))}% <span class="muted">관세청 품목별 국가별 수출입실적</span></dd>` : ''}
    </dl>`;
    if (c.unofficial_notice) html += `<p class="note">${icon('i-info', 'ic--sm')}<span>${esc(c.unofficial_notice)}</span></p>`;
    const ev = (c.evidence || []).filter((e) => /^https?:\/\//.test(e.url || ''));
    if (ev.length) {
      const LV = { direct: '원문', secondary: '2차 자료', unverified: '미확인' };
      html += `<details class="more"><summary>${icon('i-chevron', 'ic--sm')}근거 문서 ${ev.length}건</summary>
        <div class="more__body"><ul class="flist" role="list">${ev.map((e) => `<li><a href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">${esc(e.title || e.url)}</a> <span class="muted">${esc(LV[e.level] || '')}</span></li>`).join('')}</ul></div></details>`;
    }

    if (v.status === ST.NA) {
      const na = fs.filter((f) => f.level === 'na');
      html += `<ul class="flist" role="list">${na.map((f) => findingHTML({ type: 'one', f })).join('')}</ul>`;
      return html + explainSlotHTML(v);
    }
    const gaps = fs.filter(isGap);
    if (!gaps.length) html += `<p class="pass-note">${icon('i-pass')}보완할 항목이 없습니다. 현재 처방·서류로 요건을 충족합니다.</p>`;
    for (const col of GAP_COLS) {
      const inCol = gaps.filter((f) => colOf(f) === col.id).sort((a, b) => (a.level === 'fail' ? -1 : 0) - (b.level === 'fail' ? -1 : 0));
      if (!inCol.length) continue;
      const items = groupFindings(inCol);
      html += `<section class="dgroup dgroup--${col.id}" aria-label="${esc(col.label)}">
        <h4 class="dgroup__title">${icon(col.icon)}${esc(col.label)} <span class="dgroup__n">${inCol.length}건</span></h4>
        <ul class="flist" role="list">${items.map(findingHTML).join('')}</ul></section>`;
    }
    const info = fs.filter((f) => f.level === 'info' && f.code !== 'CARD_BLOCKING_RULE');
    const rules = fs.filter((f) => f.code === 'CARD_BLOCKING_RULE');
    if (info.length) {
      const items = groupFindings(info);
      html += `<details class="more"><summary>${icon('i-chevron', 'ic--sm')}참고 정보 ${info.length}건</summary>
        <div class="more__body"><ul class="flist" role="list">${items.map(findingHTML).join('')}</ul></div></details>`;
    }
    if (rules.length) {
      html += `<details class="more"><summary>${icon('i-chevron', 'ic--sm')}이 인증의 불가 조건 ${rules.length}개</summary>
        <div class="more__body"><p class="hint">아래에 해당하면 재처방해야 합니다. 판정 엔진이 성분 규정 목록으로 함께 대조합니다.</p>
        <ul class="rules" role="list">${rules.map((f) => `<li>${icon('i-fail', 'ic--sm')}<span>${esc(clean(f.message))}</span></li>`).join('')}</ul></div></details>`;
    }
    html += explainSlotHTML(v);
    const docs = relatedDocs(v).filter((d) => S.docTypes instanceof Set && S.docTypes.has(d));
    if (docs.length) {
      html += `<div class="ddocs"><span class="ddocs__label">관련 서류 초안</span>${docs.map((d) =>
        docButton(d, docInfo(d).name, 'btn--secondary btn--sm', v.cert_id)).join('')}</div>`;
    }
    return html;
  }

  function renderTable() {
    const vs = visibleVerdicts();
    const body = $('#table-body');
    if (!vs.length) {
      body.innerHTML = '<p class="muted">이 조건에 맞는 인증이 없습니다.</p>';
      return;
    }
    const applicable = vs.filter((v) => v.status !== ST.NA);
    const na = vs.filter((v) => v.status === ST.NA);
    const groups = new Map();
    for (const v of applicable) {
      const key = isCompany(v) ? 'COMPANY' : (v.jurisdiction || '기타');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(v);
    }
    const common = commonKeys(vs);
    const worst = (list) => Math.min(...list.map((v) => RANK[v.status] ?? 9));
    const keys = Array.from(groups.keys()).sort((a, b) => (Number(a === 'COMPANY') - Number(b === 'COMPANY')) ||
      (worst(groups.get(a)) - worst(groups.get(b))) || (marketOrder(a) - marketOrder(b)) || a.localeCompare(b));

    const head = `<div class="vhead" aria-hidden="true"><span class="vhead__j">관할</span><div class="vhead__row">
      <span>판정</span><span>인증·등록 / 핵심 사유</span>
      ${GAP_COLS.map((c) => `<span class="vhead__gap">${c.lines.map((l) => `<span>${esc(l)}</span>`).join('')}</span>`).join('')}
      <span class="vhead__conf">신뢰도</span><span></span></div></div>`;

    let html = `<p class="vtable__intro">행을 누르면 근거와 해야 할 일이 펼쳐집니다. 가운데 다섯 칸은 보완이 필요한 항목 수입니다.</p>${applicable.length ? head : ''}`;
    for (const k of keys) {
      const list = groups.get(k).slice().sort((a, b) => (RANK[a.status] - RANK[b.status]) || a.cert_name.localeCompare(b.cert_name, 'ko'));
      const gid = `jg-${safeId(k)}`;
      html += `<section class="jgroup" aria-labelledby="${gid}">
        <h3 class="jgroup__name" id="${gid}">${esc(jurName(k))}${k !== 'COMPANY' && JUR[k] ? `<span class="jgroup__code">${esc(k)}</span>` : ''}</h3>
        <ul class="vlist" role="list">${list.map((v) => rowHTML(v, common)).join('')}</ul></section>`;
    }
    if (na.length) {
      html += `<details class="more na-list"><summary>${icon('i-chevron', 'ic--sm')}해당 없음 ${na.length}건 보기</summary>
        <ul class="na-items" role="list">${na.map((v) => `<li>${badge(v.status, true)}<span class="na-items__name">${esc(v.cert_name)}<span class="muted">${esc(jurName(v.jurisdiction))}</span></span>
          <span class="na-items__why">${esc(keyReason(v))}</span></li>`).join('')}</ul></details>`;
    }
    body.innerHTML = html;
  }

  // ------------------------------------------------------------------ 서류 초안
  function docInfo(id) {
    const base = DOCS.find((d) => d.id === id) || { id, name: id, desc: '' };
    const meta = S.docMeta[id] || {};
    return { id, name: meta.name || base.name, desc: meta.desc || base.desc, format: meta.format || '' };
  }
  function docButton(id, label, cls, certId) {
    return `<button type="button" class="btn ${cls}" data-doc="${esc(id)}"${certId ? ` data-doc-cert="${esc(certId)}"` : ''}>
      ${icon('i-download', 'ic--sm btn__icon')}${icon('i-loader', 'ic--sm btn__spin')}<span>${esc(label)}</span></button>`;
  }
  function renderDocs() {
    const ready = S.docTypes instanceof Set;
    const hasResult = !!S.result;
    const note = $('#docs-note');
    $('#doc-pct-wrap').hidden = !(ready && hasResult);
    if (S.docTypes === false) note.innerHTML = `${icon('i-clock', 'ic--sm')}<span>서류 초안 생성 기능을 준비하고 있습니다. 판정 결과는 그대로 볼 수 있습니다.</span>`;
    else if (!hasResult) note.innerHTML = `${icon('i-info', 'ic--sm')}<span>제품을 판정하면 결과를 반영한 초안을 내려받을 수 있습니다.</span>`;
    else {
      const vs = visibleVerdicts();
      const drafts = [].concat(...vs.map((v) => (v.findings || []).filter((f) => f.code === 'DOC_DRAFTABLE').map((f) => ({ v, f }))));
      const names = uniq(drafts.map((x) => docParts(x.f.message).short));
      const certsN = uniq(drafts.map((x) => x.v.cert_id)).length;
      const lead = names.length ? `보유 자료로 초안을 만들 수 있는 서류가 인증 ${certsN}개에 걸쳐 ${names.length}종 있습니다. ` : '';
      note.innerHTML = `${icon('i-info', 'ic--sm')}<span>${esc(lead)}${esc(S.product.name_kr)}의 판정 결과를 반영한 초안입니다. 제출 전에 담당자가 확인하고 서명합니다.</span>`;
    }
    const ids = uniq(DOCS.map((d) => d.id).concat(ready ? Array.from(S.docTypes) : []));
    $('#doclist').innerHTML = ids.map((id) => {
      const d = docInfo(id);
      const avail = ready && S.docTypes.has(id);
      let btn;
      if (!avail) btn = `<button type="button" class="btn btn--secondary" disabled>${icon('i-clock', 'ic--sm')}<span>준비 중</span></button>`;
      else if (!hasResult) btn = `<button type="button" class="btn btn--secondary" disabled>${icon('i-download', 'ic--sm')}<span>내려받기</span></button>`;
      else btn = docButton(id, '내려받기', 'btn--secondary');
      const fmt = { docx: 'Word', xlsx: 'Excel', pdf: 'PDF', md: '텍스트', txt: '텍스트', csv: 'CSV' }[String(d.format).toLowerCase()] || '';
      return `<li class="doc">${icon('i-file', 'ic--lg')}<div><h3 class="doc__name">${esc(d.name)}${fmt ? `<span class="tag">${esc(fmt)}</span>` : ''}</h3>
        <p class="doc__desc">${esc(d.desc)}</p><p class="doc__msg" id="docmsg-${safeId(id)}" role="status"></p></div>${btn}</li>`;
    }).join('');
  }
  function fileNameFrom(cd) {
    if (!cd) return '';
    const star = cd.match(/filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/);
    if (star) { try { return decodeURIComponent(star[1].trim().replace(/^"|"$/g, '')); } catch (e) { /* 아래 filename= 사용 */ } }
    const plain = cd.match(/filename\s*=\s*"?([^";]+)"?/);
    return plain ? plain[1].trim() : '';
  }
  async function downloadDoc(btn) {
    const id = btn.dataset.doc;
    const certId = btn.dataset.docCert;
    if (!S.result || btn.getAttribute('aria-busy') === 'true') return;
    const verdicts = certId ? (S.result.verdicts || []).filter((v) => v.cert_id === certId) : visibleVerdicts();
    const msg = document.getElementById(`docmsg-${safeId(id)}`);
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    try {
      const pct = $('#doc-pct');
      const res = await postJSON(`api/docs/${encodeURIComponent(id)}`, {
        product: S.product, company: S.company, verdicts, include_pct: pct ? pct.checked : true,
      });
      const blob = await res.blob();
      const name = fileNameFrom(res.headers.get('content-disposition')) || `${id}_${safeId(S.product.id || 'product')}.txt`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 2000);
      const text = `내려받았습니다: ${name}`;
      if (msg) { msg.className = 'doc__msg doc__msg--ok'; msg.textContent = text; }
      announce(text);
    } catch (err) {
      const text = err instanceof ApiError && (err.status === 404 || err.status === 405)
        ? '이 서류 초안은 아직 준비 중입니다.' : `초안을 만들지 못했습니다. ${explain(err)}`;
      if (msg) { msg.className = 'doc__msg doc__msg--err'; msg.textContent = text; }
      announce(text);
    } finally {
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
    }
  }

  // ------------------------------------------------------------------ 판정 실행
  function setTriggerBusy(trigger, on) {
    if (!trigger) return;
    if (on) trigger.setAttribute('aria-busy', 'true'); else trigger.removeAttribute('aria-busy');
    if (trigger.id === 'm-submit') {
      trigger.disabled = on;
      trigger.querySelector('.btn__text').textContent = on ? '판정 중' : '판정하기';
    }
  }
  function renderEvalError(err, retry) {
    const text = explain(err);
    if (!text) return;
    S.retry = retry;
    resetSummaryTitle();
    $('#summary-body').innerHTML = `<div class="state" role="alert">${icon('i-alert')}<div>
      <p class="state__title">판정하지 못했습니다.</p><p class="state__text">${esc(text)}</p>
      <button type="button" class="btn btn--secondary btn--sm" data-retry>${icon('i-refresh', 'ic--sm')}<span>다시 시도</span></button></div></div>`;
  }

  async function evaluate(product, source, trigger) {
    if (S.ctrl) S.ctrl.abort();
    const ctrl = new AbortController();
    S.ctrl = ctrl;
    S.trigger = trigger;
    $('#sheet').setAttribute('aria-busy', 'true');
    setTriggerBusy(trigger, true);
    try {
      const res = await postJSON('api/evaluate', { product, company: S.company }, { signal: ctrl.signal });
      const data = await res.json();
      if (ctrl !== S.ctrl) return;
      S.product = product;
      S.result = data;
      S.gapByCode = {};
      (data.verdicts || []).forEach((v) => (v.findings || []).forEach((f) => { if (f.gap) S.gapByCode[f.code] = f.gap; }));
      S.source = source;
      S.demoId = source === 'demo' ? product.id : null;
      S.expanded.clear();
      S.explain = {};
      S.explainGen += 1;
      if (data.disclaimer) $('#disclaimer').textContent = data.disclaimer;
      renderResult(true);
      renderDemoPressed();
      const pv = visibleVerdicts().filter((v) => !isCompany(v));
      const c = counts(pv);
      const alertN = mlState().kind === 'on' ? pv.filter((v) => mlOf(v) && mlOf(v).hidden_fail_alert).length : 0;
      announce(`판정 완료: ${product.name_kr}. 불가 ${c.fail}개, 조건부 ${c.cond}개, 통과 가능 ${c.pass}개, 해당 없음 ${c.na}개.${alertN ? ` 불가 가능성 경보 ${alertN}건.` : ''}`);
      revealSummary(source === 'manual');
    } catch (err) {
      if (err.name === 'AbortError') return;
      renderEvalError(err, () => evaluate(product, source, trigger));
      if (source === 'manual') {
        const e = $('#m-submit-err');
        e.innerHTML = `${icon('i-alert', 'ic--sm')}<span>${esc(explain(err))}</span>`;
        e.hidden = false;
      }
      announce(`판정하지 못했습니다. ${explain(err)}`);
    } finally {
      if (ctrl === S.ctrl) {
        S.ctrl = null;
        $('#sheet').setAttribute('aria-busy', 'false');
        setTriggerBusy(trigger, false);
      } else if (trigger !== S.trigger) {
        setTriggerBusy(trigger, false); // 다른 버튼으로 새 요청이 시작돼 중단된 경우만 푼다
      }
    }
  }

  function revealSummary(moveFocus) {
    const sec = $('#summary');
    const top = sec.getBoundingClientRect().top;
    const headerH = $('.top').offsetHeight;
    const visible = top >= headerH - 4 && top < window.innerHeight * 0.6;
    if (!wide() || !visible) sec.scrollIntoView({ behavior: reduceMotion() ? 'auto' : 'smooth', block: 'start' });
    if (moveFocus || !wide()) sec.focus({ preventScroll: true });
  }

  function renderResult(fresh) {
    const sheet = $('#sheet');
    sheet.classList.toggle('is-fresh', !!fresh && !reduceMotion());
    renderSummary();
    renderTable();
    renderDocs();
    renderBasis();
    if (fresh) window.setTimeout(() => sheet.classList.remove('is-fresh'), 400);
  }
  function renderDemoPressed() {
    document.querySelectorAll('.demo').forEach((b) => b.setAttribute('aria-pressed', String(S.source === 'demo' && b.dataset.demo === S.demoId)));
  }

  // ------------------------------------------------------------------ 직접 입력
  function normKey(s) { return String(s || '').toLowerCase().replace(/\s+/g, ' ').trim(); }
  function parseIngredients(text) {
    const items = [];
    let hangul = 0;
    let latin = 0;
    const base = S.fill && S.fill.base ? new Map((S.fill.base.ingredients || []).map((i) => [normKey(i.inci), i])) : null;
    for (const raw of String(text || '').split(/\r?\n/)) {
      const line = raw.trim();
      if (!line) continue;
      // 쉼표로 나누되 숫자 사이 쉼표(1,2-Hexanediol, 0,5)는 그대로 둔다. 각 조각은 'INCI | 함량' 또는 탭 구분
      const parts = line.replace(/(\d),(?=\d)/g, '$1\u0001').split(',').map((x) => x.replace(/\u0001/g, ','));
      for (let part of parts) {
        part = part.trim().replace(/^\d+[.)]\s+/, '').replace(/[.;]+$/, '');
        if (!part) continue;
        const cols = part.split(/\s*[|\t]\s*/);
        const name = (cols[0] || '').trim();
        if (!name) continue;
        let pct = null;
        if (cols[1]) {
          const m = cols[1].replace(',', '.').match(/\d+(?:\.\d+)?/);
          if (m) { const n = parseFloat(m[0]); if (n >= 0 && n <= 100) pct = n; }
        }
        const casCol = (cols[2] || '').trim();
        const isKr = /[가-힣]/.test(name);
        if (isKr) hangul += 1;
        if (/[A-Za-z]/.test(name) && !isKr) latin += 1;
        const known = base && base.get(normKey(name));
        const ing = { inci: name, kr: isKr ? name : (known && known.kr) || null, pct, cas: /^\d{2,7}-\d{2}-\d$/.test(casCol) ? casCol : (known && known.cas) || null };
        if (known && known.role) ing.role = known.role;
        items.push(ing);
      }
    }
    return { items, hangul, latin };
  }
  function updateParse() {
    const r = parseIngredients($('#m-ing').value);
    const out = $('#m-ing-parse');
    const withPct = r.items.filter((i) => i.pct != null).length;
    let text = `인식된 성분 ${r.items.length}종${r.items.length ? `(함량 있음 ${withPct}종)` : ''}`;
    if (r.hangul) {
      text += ` — 한글 성분명 ${r.hangul}종은 식약처 원료성분 사전으로 영문 INCI로 바꿔 대조합니다. 사전에 없는 이름은 결과에 따로 알려 드립니다.`;
      out.className = 'parse parse--warn';
      out.innerHTML = `${icon('i-cond', 'ic--sm')}<span>${esc(text)}</span>`;
    } else {
      out.className = 'parse';
      out.textContent = text;
    }
    return r;
  }
  // ------------------------------------------------------------------ 포장 사진 OCR
  const OCR_LONG_SIDE = 2400; // 서버 본문 상한(8 MiB) 아래로 줄이면서 작은 성분 글자는 남기는 크기
  const OCR_ANGLES = [0, 90, 270]; // 성분이 거의 안 나오면 옆으로 누운 사진으로 보고 돌려서 다시 읽는다
  const OCR_ENOUGH = 3; // 사전과 정확히 맞은 성분이 이 개수 이상이면 더 돌려 보지 않는다
  function shrinkPhoto(file, deg = 0) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const s = Math.min(1, OCR_LONG_SIDE / Math.max(img.naturalWidth, img.naturalHeight));
        const w = Math.round(img.naturalWidth * s);
        const h = Math.round(img.naturalHeight * s);
        const c = document.createElement('canvas');
        const side = deg % 180 !== 0;
        c.width = side ? h : w;
        c.height = side ? w : h;
        const g = c.getContext('2d');
        g.translate(c.width / 2, c.height / 2);
        g.rotate((deg * Math.PI) / 180);
        g.drawImage(img, -w / 2, -h / 2, w, h);
        URL.revokeObjectURL(url);
        c.toBlob((b) => (b ? resolve(b) : reject(new Error('사진을 줄이지 못했습니다.'))), 'image/jpeg', 0.9);
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('사진을 열지 못했습니다. JPEG·PNG·WebP 사진인지 확인하세요.')); };
      img.src = url;
    });
  }
  function ocrResultHTML(r) {
    const c = r.counts || {};
    const items = r.ingredients || [];
    if (!items.length) {
      const lines = (r.lines || []).slice(0, 12).map((l) => `<li>${esc(l.text)}</li>`).join('');
      return `<p class="parse parse--warn">${icon('i-cond', 'ic--sm')}<span>사진에서 글자 ${esc(r.words)}개를 읽었지만 "전성분" 표기를 찾지 못했습니다. 전성분 부분이 화면 가운데 오게 다시 찍어 주세요.</span></p>
        ${lines ? `<details class="ocr-out__raw"><summary>읽은 글자 보기</summary><ul>${lines}</ul></details>` : ''}`;
    }
    const check = items.filter((i) => i.match !== 'exact');
    const rows = check.map((i) => (i.match === 'fuzzy'
      ? `<li><span class="ocr-out__tag ocr-out__tag--fuzzy">이름 맞춤</span> 읽은 글자 <q>${esc(i.raw)}</q> → 표준명 <strong>${esc(i.kr)}</strong> (유사도 ${esc(i.score)})</li>`
      : `<li><span class="ocr-out__tag ocr-out__tag--unknown">확인 필요</span> <q>${esc(i.raw)}</q> — 사전에 없는 이름입니다. 사진과 대조해 고쳐 주세요.</li>`)).join('');
    const how = [r.method === 'lines' ? '"전성분" 표기 대신 표의 줄마다 성분명을 사전과 대조해 찾았습니다.' : '',
      r.angle ? `사진이 옆으로 누워 있어 ${r.angle}° 돌려 읽었습니다.` : ''].filter(Boolean).join(' ');
    return `<p class="parse">${icon('i-check', 'ic--sm')}<span>전성분 ${items.length}종을 읽어 아래 칸에 채웠습니다. 식약처 사전과 그대로 일치 ${c.exact || 0}종, 비슷한 이름으로 맞춤 ${c.fuzzy || 0}종, 확인 필요 ${c.unknown || 0}종.${how ? ` ${esc(how)}` : ''}</span></p>
      ${rows ? `<ul class="ocr-out__list">${rows}</ul>` : ''}`;
  }
  async function readPhoto(file) {
    const btn = $('#m-photo-btn');
    const out = $('#m-photo-out');
    btn.setAttribute('aria-busy', 'true');
    btn.disabled = true;
    out.hidden = false;
    out.innerHTML = `<p class="parse">${icon('i-clock', 'ic--sm')}<span>사진을 읽는 중입니다. 서빙이 쉬고 있었다면 첫 응답에 시간이 더 걸립니다.</span></p>`;
    try {
      let r = null;
      for (const deg of OCR_ANGLES) {
        if (deg) out.innerHTML = `<p class="parse">${icon('i-clock', 'ic--sm')}<span>성분을 거의 찾지 못해 사진을 ${deg}° 돌려 다시 읽는 중입니다.</span></p>`;
        const blob = await shrinkPhoto(file, deg);
        const res = await fetch('api/ocr', { method: 'POST', headers: { 'Content-Type': 'image/jpeg', Accept: 'application/json' }, body: blob });
        if (!res.ok) throw await readError(res);
        const got = { ...(await res.json()), angle: deg };
        if (!r || (got.counts?.exact || 0) > (r.counts?.exact || 0)) r = got;
        if ((r.counts?.exact || 0) >= OCR_ENOUGH) break;
      }
      out.innerHTML = ocrResultHTML(r);
      if ((r.ingredients || []).length) {
        $('#m-ing').value = r.ingredients.map((i) => i.kr || i.raw).join('\n');
        updateParse();
        fieldError('m-ing-err', 'm-ing', '');
      }
      announce(r.ingredients && r.ingredients.length ? `전성분 ${r.ingredients.length}종을 채웠습니다.` : '전성분 표기를 찾지 못했습니다.');
    } catch (err) {
      out.innerHTML = `<p class="field__err">${icon('i-alert', 'ic--sm')}<span>${esc(err instanceof ApiError ? explain(err) : err.message)}</span></p>`;
    } finally {
      btn.removeAttribute('aria-busy');
      btn.disabled = false;
      $('#m-photo').value = '';
    }
  }
  function fieldError(id, inputId, text) {
    const e = document.getElementById(id);
    const input = inputId ? document.getElementById(inputId) : null;
    if (text) {
      e.innerHTML = `${icon('i-alert', 'ic--sm')}<span>${esc(text)}</span>`;
      e.hidden = false;
      if (input) input.setAttribute('aria-invalid', 'true');
    } else {
      e.hidden = true;
      e.textContent = '';
      if (input) input.removeAttribute('aria-invalid');
    }
  }
  function checkedValues(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map((i) => i.value);
  }
  function buildManualProduct() {
    const r = parseIngredients($('#m-ing').value);
    if (!r.items.length) return { error: '전성분을 한 줄 이상 입력하세요.' };
    const base = (S.fill && S.fill.base) || {};
    const claims = uniq(checkedValues('m-claim').concat((S.fill && S.fill.extraClaims) || []));
    const docs = uniq(checkedValues('m-doc').concat((S.fill && S.fill.extraDocs) || []));
    const mfr = checkedValues('m-mfr');
    const mfrCerts = uniq([].concat(...mfr.map((v) => (v === 'CGMP' ? ['CGMP', 'ISO 22716'] : ['HALAL']))).concat((S.fill && S.fill.extraMfr) || []));
    const withPct = r.items.filter((i) => i.pct != null).length;
    const name = $('#m-name').value.trim() || (base.name_kr ? `${base.name_kr} (수정)` : '직접 입력 제품');
    const product = Object.assign({}, base, {
      id: base.id ? `${base.id}-edit` : 'U1',
      name_kr: name,
      status: base.status || 'user_input',
      product_type: base.product_type || 'cosmetic',
      application: (document.querySelector('input[name="m-app"]:checked') || {}).value || 'leave_on',
      claims,
      functional_kr: claims.filter((c) => FUNCTIONAL.has(c)),
      documents: docs,
      formula_known: withPct === r.items.length ? 'full_with_concentration' : withPct ? 'partial_concentration' : 'ingredients_only_no_concentration',
      manufacturer: Object.assign({ name: '위탁제조사', country: 'KR' }, base.manufacturer || {}, { certs: mfrCerts }),
      ingredients: r.items,
    });
    return { product };
  }
  function fillFromDemo(id) {
    const p = ((S.demo && S.demo.products) || []).find((x) => x.id === id);
    const extrasEl = $('#m-extras');
    if (!p) { S.fill = null; extrasEl.hidden = true; return; }
    $('#m-name').value = `${p.name_kr} (수정)`;
    $('#m-ing').value = (p.ingredients || []).map((i) => (typeof i.pct === 'number' ? `${i.inci} | ${i.pct}` : i.inci)).join('\n');
    const app = document.querySelector(`input[name="m-app"][value="${p.application === 'rinse_off' ? 'rinse_off' : 'leave_on'}"]`);
    if (app) app.checked = true;
    const claims = uniq([].concat(p.claims || [], p.functional_kr || []));
    const claimVals = new Set(CLAIM_OPTS.map(([v]) => v));
    document.querySelectorAll('input[name="m-claim"]').forEach((i) => { i.checked = claims.includes(i.value); });
    const docs = p.documents || [];
    const matchedDocs = new Set();
    document.querySelectorAll('input[name="m-doc"]').forEach((i) => {
      const hit = docs.filter((d) => d.toLowerCase().startsWith(i.value.toLowerCase()));
      i.checked = hit.length > 0;
      hit.forEach((d) => matchedDocs.add(d));
    });
    const certs = (p.manufacturer && p.manufacturer.certs) || [];
    const certText = certs.join(' ').toLowerCase();
    document.querySelectorAll('input[name="m-mfr"]').forEach((i) => {
      i.checked = i.value === 'CGMP' ? /cgmp|22716/.test(certText) : /halal/.test(certText);
    });
    S.fill = {
      base: p,
      extraClaims: claims.filter((c) => !claimVals.has(c)),
      extraDocs: docs.filter((d) => !matchedDocs.has(d)),
      extraMfr: certs.filter((c) => !/cgmp|22716|halal/i.test(c)),
    };
    const ex = [];
    if (S.fill.extraClaims.length) ex.push(`표방 ${S.fill.extraClaims.length}개(${claimText(S.fill.extraClaims).slice(0, 3).join(', ')}${S.fill.extraClaims.length > 3 ? ' 등' : ''})`);
    if (S.fill.extraDocs.length) ex.push(`서류 ${S.fill.extraDocs.length}개`);
    extrasEl.textContent = ex.length ? `목록에 없는 ${ex.join(', ')}는 불러온 그대로 판정에 넣습니다.` : '';
    extrasEl.hidden = !ex.length;
    updateParse();
    fieldError('m-ing-err', 'm-ing', '');
  }

  // ------------------------------------------------------------------ 이벤트
  function selectTab(tab, focus) {
    const tabs = Array.from(document.querySelectorAll('.tabs__tab'));
    for (const t of tabs) {
      const on = t === tab;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      document.getElementById(t.getAttribute('aria-controls')).hidden = !on;
    }
    if (focus) tab.focus();
  }
  function bindEvents() {
    const tabs = Array.from(document.querySelectorAll('.tabs__tab'));
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => selectTab(t));
      t.addEventListener('keydown', (e) => {
        let j = null;
        if (e.key === 'ArrowRight') j = (i + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') j = (i - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') j = 0;
        else if (e.key === 'End') j = tabs.length - 1;
        if (j != null) { e.preventDefault(); selectTab(tabs[j], true); }
      });
    });

    $('#demo-list').addEventListener('click', (e) => {
      const b = e.target.closest('.demo');
      if (!b) return;
      const p = ((S.demo && S.demo.products) || []).find((x) => x.id === b.dataset.demo);
      if (p) evaluate(p, 'demo', b);
    });

    $('#filter-chips').addEventListener('change', (e) => {
      if (e.target.name !== 'filter') return;
      S.filter = e.target.value;
      if (S.result) {
        renderResult(false);
        const c = counts(visibleVerdicts());
        announce(`판정 대상: ${filterDef().label}. 인증 ${c.fail + c.cond + c.pass + c.na}개를 보여 줍니다.`);
      }
    });

    let parseTimer = null;
    $('#m-ing').addEventListener('input', () => {
      window.clearTimeout(parseTimer);
      parseTimer = window.setTimeout(updateParse, 150);
    });
    $('#m-ing').addEventListener('blur', () => {
      if ($('#m-ing').value.trim()) fieldError('m-ing-err', 'm-ing', '');
    });
    $('#m-fill').addEventListener('change', (e) => fillFromDemo(e.target.value));
    $('#m-photo-btn').addEventListener('click', () => $('#m-photo').click());
    $('#m-photo').addEventListener('change', (e) => { if (e.target.files && e.target.files[0]) readPhoto(e.target.files[0]); });
    $('#manual-form').addEventListener('submit', (e) => {
      e.preventDefault();
      fieldError('m-submit-err', null, '');
      const r = buildManualProduct();
      if (r.error) {
        fieldError('m-ing-err', 'm-ing', r.error);
        $('#m-ing').focus();
        return;
      }
      fieldError('m-ing-err', 'm-ing', '');
      evaluate(r.product, 'manual', $('#m-submit'));
    });

    document.addEventListener('click', (e) => {
      const row = e.target.closest('.vrow__btn');
      if (row) { toggleRow(row); return; }
      const doc = e.target.closest('[data-doc]');
      if (doc && !doc.disabled) { downloadDoc(doc); return; }
      const again = e.target.closest('[data-explain-retry]');
      if (again) { loadExplain(again.dataset.explainRetry, true); return; }
      if (e.target.closest('[data-retry]') && S.retry) S.retry();
    });

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll, { passive: true });
  }

  function toggleRow(btn) {
    const certId = btn.dataset.cert;
    const panel = document.getElementById(btn.getAttribute('aria-controls'));
    const open = btn.getAttribute('aria-expanded') !== 'true';
    btn.setAttribute('aria-expanded', String(open));
    btn.closest('.vrow').classList.toggle('is-open', open);
    if (open) {
      const v = (S.result.verdicts || []).find((x) => x.cert_id === certId);
      if (v && !panel.dataset.ready) { panel.innerHTML = detailHTML(v); panel.dataset.ready = '1'; }
      if (v) loadExplain(certId);
      panel.hidden = false;
      S.expanded.add(certId);
    } else {
      panel.hidden = true;
      S.expanded.delete(certId);
    }
  }

  let spyFrame = 0;
  function onScroll() {
    if (spyFrame) return;
    spyFrame = window.requestAnimationFrame(() => {
      spyFrame = 0;
      const line = $('.top').offsetHeight + 16;
      let current = wide() ? 'summary' : 'input'; // 넓은 화면은 입력 영역이 늘 보이므로 판정서 기준으로 표시
      for (const id of ['summary', 'table', 'docs']) {
        const el = document.getElementById(id);
        if (el && el.getBoundingClientRect().top <= line) current = id;
      }
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4 && S.result) current = 'docs';
      document.querySelectorAll('[data-nav]').forEach((a) => {
        if (a.dataset.nav === current) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
      });
    });
  }

  // ------------------------------------------------------------------ 시작
  function normalizeDocTypes(data) {
    const ids = new Set();
    const add = (id, meta) => { if (!id) return; ids.add(String(id)); if (meta) S.docMeta[id] = meta; };
    const list = Array.isArray(data) ? data : data && Array.isArray(data.types) ? data.types : null;
    if (list) {
      for (const x of list) {
        if (typeof x === 'string') add(x);
        else if (x && typeof x === 'object') {
          const id = x.id || x.doc_type || x.type || x.key;
          add(id, { name: x.name_ko || x.name || x.label || x.title, desc: x.desc || x.description, format: x.format });
        }
      }
    } else if (data && typeof data === 'object') {
      for (const [k, v] of Object.entries(data)) {
        add(k, typeof v === 'string' ? { name: v } : v && typeof v === 'object' ? { name: v.name_ko || v.name || v.label, desc: v.desc || v.description } : null);
      }
    }
    return ids;
  }

  function renderBasis() {
    const h = S.health;
    const parts = [];
    if (h && typeof h.cards === 'number') parts.push(`인증 요건 카드 ${h.cards}종을 기준으로 판정합니다.`);
    if (h && Array.isArray(h.reg_jurisdictions) && h.reg_jurisdictions.length) parts.push(`성분 규정 목록: ${h.reg_jurisdictions.map(jurName).join(', ')}.`);
    const st = mlState();
    if (st.kind === 'on') parts.push('AIStream 판정 모델의 결과를 규칙 판정과 함께 보여 줍니다.');
    else if (st.kind === 'error') parts.push('AIStream 판정 모델이 이번 판정에 응답하지 않아 규칙 판정만 보여 줍니다.');
    else if (st.kind === 'off' || (h && h.ml_model === false)) parts.push('AIStream 판정 모델은 연결되지 않았습니다.');
    else if (h && h.ml_model) parts.push('AIStream 판정 모델이 설정되어 있습니다.');
    parts.push('데모 제품과 회사 정보는 가공한 가상 데이터입니다.');
    $('#basis').textContent = parts.join(' ');
  }

  async function init() {
    bindEvents();
    renderEmpty();
    const [health, certs, demo, docs] = await Promise.allSettled([
      getJSON('api/health'), getJSON('api/certs'), getJSON('api/demo-products'), getJSON('api/docs/types'),
    ]);
    if (health.status === 'fulfilled') S.health = health.value;
    // OCR 서빙이 연결되지 않은 서버에서는 사진 입력 칸을 숨긴다
    $('#m-photo-field').hidden = !(S.health && S.health.ocr_model);
    if (certs.status === 'fulfilled' && Array.isArray(certs.value)) {
      S.certs = certs.value;
      S.certIndex = Object.fromEntries(S.certs.map((c) => [c.id, c]));
    }
    if (demo.status === 'fulfilled') {
      S.demo = demo.value;
      S.company = (demo.value && demo.value.company) || {};
    }
    S.docTypes = docs.status === 'fulfilled' ? normalizeDocTypes(docs.value) : false;
    if (S.docTypes instanceof Set && !S.docTypes.size) S.docTypes = false;

    renderCompany();
    renderFilter();
    renderBasis();
    renderDocs();
    if (demo.status === 'fulfilled') {
      renderDemoList();
      renderManualOptions();
    } else {
      $('#demo-list').setAttribute('aria-busy', 'false');
      $('#demo-list').innerHTML = `<li class="state" role="alert">${icon('i-alert')}<div><p class="state__title">데모 제품을 불러오지 못했습니다.</p>
        <p class="state__text">${esc(explain(demo.reason))}</p></div></li>`;
      renderManualOptions();
    }
    if (certs.status !== 'fulfilled') {
      $('#filter-chips').insertAdjacentHTML('afterend', `<p class="field__err" role="alert">${icon('i-alert', 'ic--sm')}<span>인증 목록을 불러오지 못했습니다. ${esc(explain(certs.reason))}</span></p>`);
    }
    onScroll();

    const want = new URLSearchParams(location.search).get('demo');
    if (want && S.demo) {
      const p = (S.demo.products || []).find((x) => x.id === want);
      if (p) evaluate(p, 'demo', document.querySelector(`.demo[data-demo="${CSS.escape(want)}"]`));
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
