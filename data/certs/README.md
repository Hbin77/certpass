> 2026-11-07 운영처 검토 반영: COSMOS 기준서·승인 원료 DB는 저작권 문구(서면 허락 없는 복제·이용 제한) 때문에 쓰지 않는다. COSMOS 천연·유기농·ECOCERT 카드 3장은 공개 사실 기반 `NATURAL_ORGANIC_PRESCREEN` 1장으로 대체했고, 민간 인증기관·기사·번역 출처는 문서명과 링크만 둔다(원문 인용 없음).

# 인증 요건 카드(data/certs)

- 작성: 2026-11-07 (규제 데이터 담당). 카드 58장 = 인증·등록 1개당 YAML 1개(`{id}.yaml`), 583종 중 해당 없음(N) 487종은 `_not_applicable.csv` 한 파일.
- 엔진은 이 폴더의 `*.yaml`을 모두 읽는다(`certcheck/data.py: load_cards`). 판정 등급 정의는 엔진과 같다 — **불가**: 재처방(포장재 변경 포함)해야만 통과 / **조건부**: 서류·현지 책임자·표방 문구·시험·원료 증명·미확인 데이터 보완으로 통과 / **통과 가능**: 현재 처방·서류로 통과 / **해당 없음**: 제품 유형·표방이 적용 대상이 아님.
- 원칙: 원문으로 확인한 것만 단정하고, 일반 지식으로 채운 부분은 문장 끝에 **(추정)**, 근거 항목은 `level: unverified`로 둔다. 컨설팅·KOTRA·언론 등 2차 자료로만 확인한 부분은 **(2차)**, 근거 항목은 `level: secondary`. 날짜·수치는 원문 그대로.

## 1. 근거 수준 표기

| 표기 | 뜻 |
|---|---|
| `evidence.level: direct` | 원문 파일을 직접 열어 확인(로컬 `local:` 경로, 공식 문서·법령 전재본 URL) 또는 조사정리 문서에서 ◎로 표시된 출처. 2026-11-07 국가별 조사분은 `quote`에 원문 문장(원어, 15단어 이내)을 붙였다 |
| `evidence.level: secondary` | 조사정리 문서의 ○(검색 요약), 583종 분류표 비고(`cos_note`), 국가별 조사의 2차 자료(컨설팅·KOTRA·언론·법령 미러 중 2차로 분류된 것) |
| `evidence.level: unverified` | 일반 지식 기반 출처 후보(주소만 적음, 열어 보지 않음) |
| 본문 **(2차)** | 2차 자료로만 확인 — 원문 대조 전까지 단정하지 말 것 |
| 카드 근거 수준 **원문** | 핵심 요건(누가·무엇을·언제)을 원문으로 확인. 세부 항목 일부는 (추정) |
| 카드 근거 수준 **일부 원문** | 핵심 중 일부(예: 의무 시행일, 인정 기관)만 원문, 서류·절차는 (추정) |
| 카드 근거 수준 **2차+추정** | 583종 분류 비고 수준의 2차 근거와 일반 지식 — 국가별 조사 결과로 교체 필요 |

`url`이 `local:`로 시작하면 프로젝트 루트(`contest/진행/ax혁신/`) 기준 상대 경로다. `quote`(선택)는 원문 인용문.

## 2. 카드 목록

(추정) 표시 합계 354개. 근거 수 = direct/secondary/unverified 항목 수.

### 전략인증 5종 (5장)

| id | 이름 | kind | 근거 수준 | 근거 수(d/s/u) | (추정) 수 | 583종 번호 |
|---|---|---|---|---|---|---|
| `EU_CPNP` | EU 화장품 신고(CPNP) | mandatory_registration | 원문 | 5/0/2 | 15 | - |
| `UK_SCPN` | 영국 화장품 신고(SCPN) | mandatory_registration | 원문 | 4/0/0 | 15 | - |
| `US_MOCRA` | 미국 FDA 화장품 시설등록·제품리스팅(MoCRA) | mandatory_registration | 원문 | 4/0/2 | 15 | 43 |
| `EU_PPWR` | EU 포장 및 포장폐기물 규정(PPWR) | packaging | 일부 원문 | 1/1/1 | 17 | - |
| `HALAL` | 할랄 인증(화장품, 국제) | voluntary_certification | 원문 | 11/1/0 | 0 | - |

### 국가 등록(583종 A) (24장)

| id | 이름 | kind | 근거 수준 | 근거 수(d/s/u) | (추정) 수 | 583종 번호 |
|---|---|---|---|---|---|---|
| `CN_NMPA_GENERAL` | 중국 일반화장품 备案(NMPA) | mandatory_registration | 원문 | 3/0/1 | 12 | 349 |
| `CN_NMPA_SPECIAL` | 중국 특수화장품 注册(NMPA, 미백 포함) | mandatory_registration | 원문 | 2/0/1 | 8 | 349 |
| `JP_COSMETIC_NOTIFICATION` | 일본 화장품 製造販売届 + 외국제조업자届 | mandatory_registration | 원문 | 5/0/1 | 19 | 235 |
| `JP_QUASI_DRUG` | 일본 의약부외품(약용화장품) 製造販売承認 | mandatory_registration | 일부 원문 | 1/1/1 | 22 | 235 |
| `TW_TFDA` | 대만 화장품 제품 등록(登錄)·PIF | mandatory_registration | 원문 | 4/0/0 | 15 | 273 |
| `MY_NPRA` | 말레이시아 화장품 노티피케이션(NPRA) | mandatory_registration | 원문 | 8/1/0 | 3 | 261 |
| `ID_BPOM` | 인도네시아 화장품 노티피카시(BPOM) | mandatory_registration | 원문 | 9/2/0 | 3 | 317 |
| `TH_FDA` | 태국 화장품 노티피케이션(Thai FDA) | mandatory_registration | 원문 | 8/1/0 | 3 | 278 |
| `PH_FDA` | 필리핀 화장품 노티피케이션(FDA Philippines) | mandatory_registration | 원문 | 7/1/0 | 5 | 388 |
| `VN_DAV` | 베트남 화장품 공고(DAV) | mandatory_registration | 원문 | 7/1/0 | 3 | 391 |
| `SG_HSA` | 싱가포르 화장품 노티피케이션(HSA) | mandatory_registration | 원문 | 7/1/0 | 2 | 293 |
| `IN_CDSCO` | 인도 수입 화장품 등록(CDSCO) | mandatory_registration | 원문 | 6/1/1 | 3 | 305 |
| `SA_SFDA` | 사우디 화장품 신고(SFDA eCosma) | mandatory_registration | 원문 | 3/0/0 | 9 | 288 |
| `CA_CNF` | 캐나다 화장품 사전신고(CNF) | mandatory_registration | 원문 | 1/0/1 | 18 | 361 |
| `BR_ANVISA` | 브라질 화장품 신고·등록(ANVISA) | mandatory_registration | 원문 | 7/1/0 | 1 | 281 |
| `AR_ANMAT` | 아르헨티나 화장품 등록(ANMAT) | mandatory_registration | 2차+추정 | 0/1/1 | 15 | 300 |
| `CO_INVIMA` | 콜롬비아 화장품 의무위생신고(INVIMA NSO) | mandatory_registration | 원문 | 6/1/1 | 1 | 376 |
| `PE_DIGEMID` | 페루 화장품 위생신고(DIGEMID NSO) | mandatory_registration | 원문 | 5/1/0 | 0 | 374 |
| `EG_EDA` | 이집트 화장품 등록(EDA) | mandatory_registration | 원문 | 8/1/0 | 0 | 440 |
| `MA_DMP` | 모로코 화장품 사전등록(DMP) | mandatory_registration | 2차+추정 | 1/2/1 | 4 | 435 |
| `IR_MOH` | 이란 화장품 등록(보건부 IFDA) | mandatory_registration | 2차+추정 | 1/2/1 | 8 | 425 |
| `MM_FDA` | 미얀마 화장품 등록(Myanmar FDA) | mandatory_registration | 2차+추정 | 2/1/1 | 2 | 438 |
| `KH_DDF` | 캄보디아 화장품 등록(DDF) | mandatory_registration | 일부 원문 | 4/1/0 | 3 | 448 |
| `EAEU_TRCU009` | 유라시아경제연합 화장품 적합성 선언(TR CU 009/2011, EAC) | mandatory_compliance | 원문 | 6/1/0 | 4 | 478 |

### 조건부 적용(583종 B) (9장)

| id | 이름 | kind | 근거 수준 | 근거 수(d/s/u) | (추정) 수 | 583종 번호 |
|---|---|---|---|---|---|---|
| `US_PROP65` | 미국 캘리포니아 Prop 65 경고 표시 | mandatory_compliance | 2차+추정 | 0/1/1 | 14 | 22 |
| `EU_REACH_D4D5D6` | EU REACH 사이클로실록산(D4·D5·D6) 제한 | mandatory_compliance | 원문 | 2/1/1 | 6 | 130 |
| `EU_ECOLABEL_RINSEOFF` | EU 에코라벨(씻어내는 화장품) | voluntary_certification | 2차+추정 | 0/1/1 | 15 | 118 |
| `MX_COFEPRIS_NOM141` | 멕시코 화장품 규정 준수(COFEPRIS·NOM-141 라벨) | mandatory_compliance | 원문 | 5/1/0 | 2 | 263 |
| `AU_AICIS` | 호주 산업화학물질 도입제도(AICIS) — 화장품 수입자 등록 | chemical_registration | 원문 | 9/0/0 | 5 | - |
| `NZ_HSNO_COSMETIC` | 뉴질랜드 화장품 그룹 표준(HSNO) | mandatory_compliance | 원문 | 7/1/0 | 4 | 501 |
| `EAEU_SGR` | 유라시아 국가위생등록(SGR) — 미백·어린이용 등 특정 화장품 | mandatory_registration | 원문 | 4/1/0 | 3 | 254 |
| `UAE_ECAS_GSO1943` | UAE 화장품 적합성 인증(ECAS, GSO 1943) | mandatory_registration | 원문 | 7/1/0 | 1 | 428 |
| `RSPO` | RSPO 지속가능 팜유 공급망 인증 | voluntary_certification | 2차+추정 | 0/1/1 | 11 | 553 |

### 민간 인증 (12장)

| id | 이름 | kind | 근거 수준 | 근거 수(d/s/u) | (추정) 수 | 583종 번호 |
|---|---|---|---|---|---|---|
| `NATURAL_ORGANIC_PRESCREEN` | 천연·유기농 인증 사전 점검(공통 원칙, 공개 사실만) | voluntary_certification | 일부 원문 | 1/2/0 | 0 | 112·155·193 |
| `NATRUE` | NATRUE 천연·유기농 화장품 라벨 | voluntary_certification | 원문 | 6/1/0 | 0 | 137 |
| `VEGAN_KOREA` | 한국비건인증원 비건 인증 | marketing_label | 원문 | 7/0/0 | 3 | - |
| `VEGAN_SOCIETY` | 영국 비건협회 비건 트레이드마크 | marketing_label | 원문 | 6/0/0 | 3 | 572 |
| `V_LABEL` | V-Label 비건 인증 | marketing_label | 원문 | 6/1/0 | 2 | 573 |
| `LEAPING_BUNNY` | 리핑버니(크루얼티프리) 인증 | marketing_label | 원문 | 8/0/0 | 1 | - |
| `USDA_ORGANIC` | 미국 USDA 유기농(NOP) 인증 — 화장품 | voluntary_certification | 원문 | 6/1/0 | 1 | 99 |
| `ECARF` | ECARF 알레르기 친화 인증 | marketing_label | 2차+추정 | 0/1/1 | 14 | 115 |
| `DERMATEST` | Dermatest 피부 저자극 인증(독일) | marketing_label | 2차+추정 | 0/1/1 | 12 | 158 |
| `KOSHER` | 코셔 인증(화장품) | marketing_label | 2차+추정 | 0/1/0 | 12 | 527 |

### 국내 필수·회사 인증 (8장)

| id | 이름 | kind | 근거 수준 | 근거 수(d/s/u) | (추정) 수 | 583종 번호 |
|---|---|---|---|---|---|---|
| `KR_RESPONSIBLE_SELLER` | 화장품책임판매업 의무·포장 표시·표시광고(국내) | mandatory_registration | 원문 | 4/0/0 | 4 | - |
| `KR_FUNCTIONAL_REPORT` | 기능성화장품 보고·심사(식약처) | mandatory_registration | 원문 | 4/0/0 | 2 | - |
| `KR_CGMP` | 우수화장품 제조·품질관리기준(CGMP) 적합업소 — 위탁제조사 확인 | voluntary_certification | 원문 | 3/0/0 | 3 | - |
| `KR_CFS_EXPORT` | 대한화장품협회 제조판매증명서(수출용 자유판매증명서, CFS) | mandatory_compliance | 원문 | 2/0/0 | 1 | - |
| `KR_SAFETY_ASSESSMENT` | 화장품 안전성 평가 의무화(시행 예정) | mandatory_compliance | 원문 | 2/0/0 | 0 | - |
| `KR_VENTURE` | 벤처기업 확인 | company_certification | 원문 | 3/0/0 | 2 | - |
| `KR_INNOBIZ` | 이노비즈(기술혁신형 중소기업) 인증 | company_certification | 원문 | 2/0/1 | 3 | - |
| `KR_MAINBIZ` | 메인비즈(경영혁신형 중소기업) 인증 | company_certification | 원문 | 2/0/1 | 3 | - |

**(추정)이 많은 카드 상위 10**: `JP_QUASI_DRUG`(22), `JP_COSMETIC_NOTIFICATION`(19), `CA_CNF`(18), `EU_PPWR`(17), `EU_CPNP`(15), `US_MOCRA`(15), `AR_ANMAT`(15), `EU_ECOLABEL_RINSEOFF`(15), `ECARF`(14), `TW_TFDA`(15)

## 3. 엔진이 읽는 필드와 값 규약

엔진(`certcheck/classify.py`, 2026-11-07 12:41 판 확인 — 다른 작업자가 성분 예외·시험 충족 판정을 고친 판)이 실제로 쓰는 필드는 아래와 같다. `blocking_rules`는 화면 표시(info)만 하고, 예외로 회사 카드는 규칙 문장에 '자본잠식'이 있고 `company.financial.capital_impairment == complete`이면 불가로 판정한다. `conditional_rules`는 아직 평가하지 않는다(태그 문법은 4절, 향후 규칙 평가용).

| 필드 | 규약 |
|---|---|
| `applies_to.product_types` | `cosmetic`이면 모든 화장품. 그 밖의 값(예: `whitening`, `sunscreen`, `cleanser_foam`)은 제품의 `product_type`·`claims`·`functional_kr`(`_planned` 제거)와 하나라도 겹쳐야 적용 |
| `applies_to.claims_any`, `condition` 안의 `[kw:claim(a\|b)]` | 있으면 그 표방이 있어야 적용(없으면 해당 없음). condition의 다른 태그(`target_market` 등)는 엔진이 아직 읽지 않음 — 현재 엔진은 모든 카드를 모든 제품에 평가하므로, 목표 국가 필터가 필요하면 카드의 `jurisdiction`으로 거를 것 |
| `jurisdiction` | 관할 코드. 회원국은 EU, 북아일랜드는 EU, 러·카자흐 등은 EAEU, 민간 인증은 GLOBAL |
| `ingredient_rules` | 성분규제 통합표에서 쓸 관할: EU/CN/JP/TW/ASEAN/none. **ASEAN = EU 행으로 대리 판정**(엔진 PROXY). 통합표에 없는 나라(사우디·인도·남미·EAEU 등)는 EU를 대용값으로 적고, 그 카드에서는 성분 규칙을 conditional에만 둠(대용 목록으로 '불가'를 내지 않기 위함). **주의: 현재 엔진은 `ingredient_rules: EU`면 대용 카드여도 EU 금지 성분을 '불가'로 판정한다**(지금 제품 4종에는 EU 금지 성분이 없어 영향 없음 — 엔진 변경 필요). 이집트(`EG_EDA`)는 EU 부속서 II~VI를 그대로 채택(원문)해 blocking에 둠. 미국·캐나다·호주·한국 등 대용이 부적절한 곳은 none + `ingredient_list_unavailable` 태그 |
| `claim_rules[].claim` | **제품 데이터 `claims` 토큰을 그대로 씀**: `whitening`, `anti_wrinkle`, `paraben_free`, `free_from_21`, `silicone_free`, `natural_origin_ingredients`, `skin_irritation_tested`, `skin_barrier`, `all_in_one`, `deep_cleansing`. 데이터에 없는 표방은 엔진 어휘: `sunscreen`, `acne`, `hair_dye`, `hair_loss`, `perm`, `children`, `anti_dandruff`, `antibacterial`, `new_efficacy`, `medical`(치료 표현), `hypoallergenic`, `organic`, `vegan`, `halal`, `kosher`, `cruelty_free`, `sustainable_palm` |
| `claim_rules[].effect` | `ok`(허용) / `needs_special_registration`(별도 등록 경로 — note의 `→ 카드ID`) / `quasi_drug`(일본 의약부외품) / `drug_risk`(의약품 판단 위험) / `not_allowed`(사용 불가) / `needs_evidence`(실증 자료 필요). ok 외에는 모두 **조건부**(문구 수정·별도 경로·실증)로 처리 — 표방만으로 '불가'를 내지 않음. KR 카드의 `needs_special_registration`·`not_allowed`는 `functional_kr`(계획 단계 `_planned` 제외)에 같은 값이 있으면 엔진이 허용 처리. 선택 키 `actives_any`(effect ok와 함께): 승인 전례 유효성분 목록 — 처방에 하나도 없으면 조건부(현재 `JP_QUASI_DRUG`) |
| `local_entity` | `required: true`면 `company.local_entities[jurisdiction]`가 있어야 충족(키 = 관할 코드, 예 `EU`, `CN`, `JP`). `role`은 화면 문구 |
| `documents_required[].satisfied_by_hint` | 하나라도 맞으면 보유. 보유 서류 id 패턴(`*` 와일드카드, 예 `test_report_*`), `formula_known:<값>`, `manufacturer.certs:<인증>`, `company.local_entities:<관할>`, `company.role_kr:<문자열>`. `draft_from:<패턴>`은 충족이 아니라 **초안 원천**(엔진: '초안 자동 생성 가능', 조건부) |
| 앞으로 회사 서류를 넣을 때 쓸 id | `quality_procedure*`, `market_release_record*`, `safety_management_record*`, `product_standard*`, `lot_quality_record*`, `production_report*`, `ingredient_list_report*`, `manager_training*`, `cfs_kcia*`(협회 제조판매증명서), `domestic_sales_invoice*` — `company.documents`에 넣으면 해당 카드 서류가 충족됨 |
| `documents_required[].producer` | external_expert / company / manufacturer / lab / authority |
| `tests_required` | 엔진은 보유 서류 패턴으로 충족을 본다 — `heavy_metals`·`microbiology`·`microbial_limit`·`physicochemical`은 국내 완제품·벌크 성적서(`finished_product_test_report*`·`bulk_test_report*`·`test_report_*`), `stability`는 `stability_test*`, `challenge_test`는 `challenge_test*`·`preservative_efficacy*`, `patch_test`는 `skin_irritation_test*`·`patch_test*`. 값: `microbiology`, `heavy_metals`, `stability`, `challenge_test`, `physicochemical`, `packaging_compatibility`, `toxicology`, `efficacy_human`, `patch_test`, `consumer_use_test`, `local_lab_test`(수출국 지정 시험소), `biodegradability`, `aquatic_toxicity`, `packaging_heavy_metals` |
| `labeling.language` | 값이 있으면 엔진이 '현지 라벨 필요'(조건부)를 띄움. 라벨 언어 요구가 아닌 카드(민간 인증·REACH·국내 카드 등)는 null — 국내 카드는 `label_kr` 서류로 판정 |
| `labeling.allergens` | 값이 있으면 향료(parfum) 제품에 알레르겐 구성 확인을 요구. 표시 의무가 없거나 미확인인 관할(중국·일본·미국, 아세안 8개국 — ACD 부속서 III에 해당 항목 없음(원문), 호주·멕시코·브라질·인도 — 원문에 표시 조항 없음)은 null로 두고 설명은 `other`에. EU식 표시 규정이 원문으로 확인된 EU·영국·EAEU(부속서 2 №67~92)·뉴질랜드(Sch.5)·이집트, 2차로 확인된 UAE(GSO 1943)는 값을 채움 |
| `kind` | `company_certification`은 회사 단위로 1회 판정(`company_certs` 상태). `KR_CGMP`는 위탁제조사 확인용이라 제품별로 판정되도록 `voluntary_certification` |
| 카드 id로 엔진이 추가 검사하는 것 | `D4D5D6`(사이클로실록산), `PROP65`(에톡실화 원료 다이옥산), `PPWR`(포장 데이터), `VEGAN`·`V_LABEL`(성분 비건 속성), `HALAL`, `NATURAL_ORGANIC`·`USDA_ORGANIC`(공개 사실 기반 천연·유기농 원칙), `NATRUE`(성분 속성표 `data/ingredients/ingredient_attributes.csv`, 없으면 휴리스틱) |

## 4. 규칙 태그 문법(blocking_rules·conditional_rules·condition)

규칙 문자열 = 자연어 + 태그 `[kw:술어(인자)]`. 한 규칙 안의 여러 태그는 AND, 규칙끼리는 OR, 인자 안의 `|`는 OR. 데이터가 없어 평가할 수 없는 태그가 들어간 blocking 규칙은 '불가'가 아니라 '조건부'로 내릴 것.

| 술어 | 참이 되는 조건 |
|---|---|
| `ingredient_banned(J)` | 통합표 관할 J(ASEAN→EU, KR은 식약처 API)의 banned 행과 성분이 INCI·CAS로 일치 |
| `ingredient_restricted_over(J) / ingredient_restricted_conc_unknown(J)` | restricted 행 한도 초과 / 함량 미상 |
| `ingredient_positive_list_missing(J)` | 보존제·UV필터·색소 역할 성분이 J의 allowed_* 목록에 없음(TW는 EU·US·JP 허용분 예외) |
| `ingredient_not_in_inventory(CN)` | INCI·CAS가 확정된 성분이 IECIC(inventory)에 없음 — 매칭 실패는 ingredient_match_unresolved로 |
| `ingredient_match_unresolved` | INCI·CAS로 어느 목록과도 연결 못 한 성분 존재 |
| `ingredient_present(A\|B\|…)` | INCI 또는 CAS가 일치(대소문자 무시, `*` 와일드카드) |
| `ingredient_conc_over(A\|B…,pct)` | 해당 성분 함량 > pct(%) — 함량 없으면 미평가 |
| `ingredient_animal_derived / ingredient_origin_unknown(animal\|palm\|alcohol)` | 확실한 동물 유래 성분 / 기원 확인이 필요한 성분(엔진 ANIMAL_HINTS·속성표) |
| `ingredient_nano` | INCI에 '(nano)' 표기 |
| `ingredient_list_unavailable(LIST)` | 엔진이 그 목록 데이터를 갖고 있지 않음(현재 항상 참 → 조건부 안내). 예: CA_HOTLIST, GSO1943, KR_MFDS, CN_BANNED_2021_74, ASEAN_ACD, UK_ANNEX |
| `claim(a\|b) / application(leave_on\|rinse_off) / formula_known(값\|값)` | 제품 표방(claims∪functional_kr) / 사용 방식 / 처방 확보 수준 |
| `doc_missing(문서id)` | 같은 카드 documents_required의 그 id가 미충족 |
| `manufacturer_cert_missing(A\|B)` | 제품 manufacturer.certs에 A·B 모두 없음 |
| `local_entity_missing(관할)` | company.local_entities에 그 관할 키 없음 |
| `company_role_missing(문자열) / company_cert_status(키,상태) / company_fact(사실\|…) / company_age_under(년) / data_unknown(필드)` | 회사 데이터 조건. company_fact 예: full_capital_impairment, debt_ratio_over_1000, annual_production_ge_1bn_krw |
| `card_verdict(카드ID,등급\|등급)` | 다른 카드 판정 결과(예: EU_ECOLABEL은 EU_CPNP 불가면 불가) |
| `target_market(관할\|…)` | 엔진 입력의 목표 시장에 포함 |
| `date_on_or_after(YYYY-MM-DD) / date_after(YYYY-MM-DD)` | 판정일 ≥ 날짜 / 판정일 > 날짜 |
| `test_result_over(시험,한도) / animal_test_data_present` | 시험 결과 한도 초과 / 동물실험 자료 존재(데이터 없으면 미평가) |
| `manual_check(주제)` | 자동 판정 불가 — 항상 참(조건부 안내). blocking에는 쓰지 않음 |

## 5. 엔진 구현 요점

- 판정 순서: 적용 여부(`applies_to`) → 성분(`ingredient_rules`) → 표방(`claim_rules`) → 성분 속성(비건·할랄·NATRUE·천연 원칙) → 카드별 특수 검사 → 서류·시험 → 현지 책임자 → 라벨. fail 하나라도 있으면 불가, 아니면 cond가 있으면 조건부.
- 같은 시장에 경로가 둘인 경우는 짝 카드로 나눴다: 중국 `CN_NMPA_GENERAL`(일반 备案)·`CN_NMPA_SPECIAL`(미백 등 특수 注册), 일본 `JP_COSMETIC_NOTIFICATION`·`JP_QUASI_DRUG`, 유라시아 `EAEU_TRCU009`(적합성 선언)·`EAEU_SGR`(국가등록). 일반 카드에서는 특수 표방을 조건부(표방 삭제 또는 특수 경로)로, 특수 카드는 그 표방이 있을 때만 적용.
- 통합표에 없는 관할을 EU로 대용한 카드는 성분 규칙을 conditional에만 둠 — 대용 목록 일치로 '불가'를 내지 말 것(현재 엔진은 이 구분을 못 해 EU 금지 성분이면 불가를 냄 — 엔진 변경 필요). ASEAN은 EU 준용을 blocking에 씀(ACD가 EU 부속서를 따름). 단 ACD 2026-1판에는 EU 2024/996의 알부틴·알파알부틴 제한과 EU식 향료 알레르겐 표시가 없어, EU 대리 판정은 이 부분에서 아세안보다 엄격함(원문 대조). 이집트는 EU 부속서를 그대로 채택(원문).
- 아세안 8개국 카드: 향료 알레르겐 표시 의무가 없어 `labeling.allergens`를 비움. 한국 기능성 미백·주름 문구는 ACD 표방 지침('노화로 인한 생리적 변화를 예방·감소·역전' 불가, 말레이시아 지침 '멜라닌 합성 억제' 불가)에 걸려 `drug_risk`(외관 표현으로 수정, 조건부).
- 유라시아: `EAEU_SGR`은 TR CU 009 부속서 12의 국가등록 대상 13종을 `product_types`로 적용(표방 태그로 막지 않음). 미백은 `EAEU_TRCU009`에서 `needs_special_registration → EAEU_SGR`.
- 중국: 통합표 CN 금지표는 2015 규범 기준이라 2021 제74호·2026 제99호 개정분 미반영 → '통과 가능'보다 조건부가 맞음. IECIC 미등재는 표기 차이일 수 있어 조건부.
- EU: 통합표 EU banned의 D4 행(부속서 II 1388)에 INCI 'CYCLOMETHICONE'이 붙어 있어 사이클로메티콘 제품이 금지로 잡힘 — 혼합물 구성 확인 후 판정. REACH 사이클로실록산: 씻어내는 제품 D4·D5 0.1% 이상은 2020-01-31 이후 금지, 바르는 제품 전부와 씻어내는 제품 D6은 2027-06-06 이후 금지(Reg. 2024/1328 원문 대조).
- 동물실험: 중국 일반화장품은 정부 발급 GMP(한국 CGMP) + 안전평가면 독성시험 면제(2021 제32호 33조) → `KR_CGMP`가 근거. 중국 특수화장품(미백 등)은 독성시험 필수라 `LEAPING_BUNNY`·`VEGAN_SOCIETY`와 충돌.
- 인도네시아 화장품 할랄 의무는 PP 40/2026(2026-10-14)으로 2026-10-17 → **2028-10-17**로 연장(BPJPH 원문) — 판정일(2026-11-07) 기준 자발이라 `ID_BPOM` 필수 서류에서 할랄 인증서를 뺐다. 2028-10-17 이후 `HALAL` 판정 참조는 conditional_rules(`date_on_or_after` + `card_verdict`)에만 있어 엔진이 아직 평가하지 않음.
- 수입 금지·제재(이란)나 참조국 판매 이력 요구(이집트)처럼 재처방으로 풀리지 않는 시장 장벽은 등급 정의상 '불가'가 아니라 조건부로 남는다 — 카드 notes·conditional_rules(`manual_check`)에 표시.
- 국내: 메인비즈는 완전자본잠식·부채비율 1,000% 이상이면 신청 불가(회사 단위 불가). 안전성 평가 의무(`KR_SAFETY_ASSESSMENT`)는 시행 전이라 서류 요구 없음 — 시행일만 표시.
- 지원사업(`support_rate`): 문서상 '50~70%, 최대 1억'. 공통 조건(문서 §4-8 ◎): 100점 만점 65점 이상 선정, 지방 가점 1점, **공고일 전 취득 인증은 지원 제외**, 필수 서류 중소기업확인서·견적서·ESG 자가진단, 자본잠식은 무관. 583종 밖 인증은 '비공고 규격인증'으로 신청해 운영위 심의(비건 등 민간 인증도 수출에 매우 중요하면 지원 예정, 단순 마케팅·홍보용 제외 — 인증목록 원문 ◎).

## 6. 583종 화장품 분류(A·B·M·U)와 카드 대응

| 번호 | 국가 | 이름 | 분류 | 카드 | 비고 |
|---|---|---|---|---|---|
| 2 | 미국 | AAFA | M | 미작성 | AAFA 천식·알레르기 친화 — 퍼스널케어 인증 가능 |
| 21 | 미국 | BPI | B | 미작성 | BPI 생분해 — 포장재 |
| 22 | 미국 | CA Proposition 65 | B | `US_PROP65` | 미국 캘리포니아 Prop 65 — 화장품에도 적용(목록 화학물질 포함 시 경고문) |
| 43 | 미국 | FDA | A | `US_MOCRA` | 미국 FDA — MoCRA 시설등록·제품리스팅·라벨 적용 |
| 54 | 미국 | GIC Vegan | M | 미작성 | GIC Vegan — 화장품 적용 |
| 55 | 미국 | Gluten Free | M | 미작성 | Gluten Free(GFCO) — 퍼스널케어 인증 가능(마케팅) |
| 57 | 미국 | Green Seal | M | 미작성 | Green Seal GS-50 퍼스널케어 기준 존재 |
| 79 | 미국 | NOP | B | `USDA_ORGANIC` | 미국 NOP(USDA 유기농 프로그램) — 99번 USDA Organic과 같은 제도 |
| 88 | 미국 | SCS | M | 미작성 | SCS 환경인증 — 클레임 |
| 95 | 미국 | UL ECV | M | 미작성 | UL 환경성 주장 검증 — 클레임 검증 |
| 98 | 미국 | USDA Biopreferred program | M | 미작성 | USDA BioPreferred — 바이오기반 함량 인증(퍼스널케어 품목 있음) |
| 99 | 미국 | USDA Organic | B | `USDA_ORGANIC` | USDA Organic(NOP) — 농산물 유래 성분 비율 충족 시 화장품 가능 |
| 112 | 유럽 | COSMOS | A | `NATURAL_ORGANIC_PRESCREEN` | COSMOS 유기농·천연 화장품 인증(ECOCERT·BDIH·Soil Assoc 등) |
| 115 | 유럽 | ECARF | M | `ECARF` | ECARF 알레르기 친화 인증 — 화장품 적용 |
| 118 | 유럽 | Eco-Labeling | B | `EU_ECOLABEL_RINSEOFF` | EU Ecolabel — 씻어내는 화장품(rinse-off) 기준 존재 → 클렌징밤·폼 해당 |
| 130 | 유럽 | EU REACH | B | `EU_REACH_D4D5D6` | EU REACH — 화장품 성분은 수입자가 연 1톤 이상 시 등록 의무(완제품 아님) |
| 135 | 유럽 | Green Dot | B | `EU_PPWR` | Green Dot — EU 포장재 폐기물 분담금(수출 시 포장 책임) |
| 137 | 유럽 | NATRUE Label | A | `NATRUE` | NATRUE 천연·유기농 화장품 라벨 |
| 138 | 유럽 | Nordic Swan | B | 미작성 | Nordic Swan — 화장품 기준 존재 |
| 143 | 유럽 | Seedling | B | 미작성 | Seedling 생분해 — 포장재 |
| 155 | 독일 | BDIH | A | `NATURAL_ORGANIC_PRESCREEN` | BDIH — COSMOS 회원 인증기관 |
| 158 | 독일 | Dermatest | M | `DERMATEST` | Dermatest 피부저자극 — 시험 기반 마크(K뷰티 다수 사용) |
| 182 | 영국 | UK REACH | B | 미작성 | UK REACH — 동일 |
| 193 | 프랑스 | ECOCERT | A | `NATURAL_ORGANIC_PRESCREEN` | ECOCERT — 화장품 인증기관(링크 안내만) |
| 235 | 일본 | PMDA | A | `JP_COSMETIC_NOTIFICATION`, `JP_QUASI_DRUG` | 일본 PMDA — 외국제조업자 신고(C73) 경유, 미백·주름 표방 시 의약부외품 승인 심사 |
| 243 | 일본 | 일본ECO mark | U | 미작성 | 일본 에코마크 — 화장품 품목 유무 확인 |
| 254 | 러시아 | SGR | B | `EAEU_SGR` | 유라시아 SGR 위생등록 — 미백·어린이용 등 특정 화장품만 대상(미백 크림 해당 가능) |
| 261 | 말레이시아 | NPRA | A | `MY_NPRA` | 말레이시아 NPRA 화장품 노티피케이션(ACD) |
| 263 | 멕시코 | COFEPRIS | B | `MX_COFEPRIS_NOM141` | 멕시코 COFEPRIS — 화장품 사전등록 없음, 라벨 NOM-141·성분 규정 준수 |
| 265 | 멕시코 | NOM | B | `MX_COFEPRIS_NOM141` | 멕시코 NOM — NOM-141 화장품 라벨 규격 |
| 266 | 멕시코 | SSA | B | `MX_COFEPRIS_NOM141` | 멕시코 SSA 위생등록 — 화장품은 원칙적 등록 면제(확인 필요) |
| 273 | 대만 | 대만FDA | A | `TW_TFDA` | 대만 TFDA 화장품 등록·PIF(2026-07 전품목) |
| 276 | 태국 | Thailand Green Label | U | 미작성 | 태국 그린라벨 — 화장품 품목 확인 |
| 278 | 태국 | 태국FDA | A | `TH_FDA` | 태국 FDA 화장품 노티피케이션 |
| 281 | 브라질 | ANVISA | A | `BR_ANVISA` | 브라질 ANVISA 화장품 노티피케이션/등록 |
| 288 | 사우디아라비아 | SFDA | A | `SA_SFDA` | 사우디 SFDA eCosma 신고 |
| 293 | 싱가포르 | HSA | B | `SG_HSA` | 싱가포르 HSA — 지원목록 설명은 의료기기이나 HSA가 화장품 노티피케이션도 관할 |
| 298 | 싱가포르 | SINGAPORE GREEN LABEL | U | 미작성 | 싱가포르 그린라벨 — 화장품 품목 확인 |
| 300 | 아르헨티나 | ANMAT | A | `AR_ANMAT` | 아르헨티나 ANMAT 화장품 등록(목록 설명은 일반) |
| 305 | 인도 | CDSCO | A | `IN_CDSCO` | 인도 CDSCO 수입 화장품 등록(동물실험 수입 금지) |
| 309 | 인도 | DCGI | B | `IN_CDSCO` | 인도 DCGI — CDSCO 수입 화장품 등록의 허가권자(305번과 같은 절차) |
| 317 | 인도네시아 | BPOM | A | `ID_BPOM` | 인도네시아 BPOM 노티피카시(+2026-10 할랄 의무) — 할랄 의무는 PP 40/2026으로 2028-10-17까지 연장(원문, 2026-11-07 확인) |
| 349 | 중국 | NMPA | A | `CN_NMPA_GENERAL`, `CN_NMPA_SPECIAL` | 중국 NMPA 일반 备案 / 미백은 특수화장품 注册 |
| 361 | 캐나다 | CNF | A | `CA_CNF` | 캐나다 CNF 화장품 사전신고 |
| 366 | 캐나다 | DSL | B | 미작성 | 캐나다 DSL — 신규 물질 신고(성분이 DSL 미등재 시) |
| 369 | 캐나다 | NHP Licensing | B | `CA_CNF` | 캐나다 NHP — 건강 효능 클레임(자외선차단 등) 제품만 |
| 372 | 쿠웨이트 | KUCAS | U | 미작성 | 쿠웨이트 KUCAS — 규제품목에 화장품 포함 여부 확인 필요 |
| 374 | 페루 | Registro sanitario | A | `PE_DIGEMID` | 페루 보건등록(DIGEMID NSOC) |
| 376 | 콜롬비아 | INVIMA | A | `CO_INVIMA` | 콜롬비아 INVIMA NSO |
| 382 | 에티오피아 | ECEA | U | 미작성 | 에티오피아 판매인증서 — EFDA 화장품 규제와 관계 확인 |
| 388 | 필리핀 | PFDA | A | `PH_FDA` | 필리핀 PFDA 화장품 노티피케이션 |
| 391 | 베트남 | DAV | A | `VN_DAV` | 베트남 DAV 화장품 등록 |
| 397 | 호주 | ABA Seedling | B | 미작성 | 호주 ABA Seedling — 포장재 |
| 413 | 호주 | TGA | B | `AU_AICIS` | 호주 TGA — 자외선차단제 등 치료용만, 일반 화장품은 AICIS(목록에 없음) |
| 416 | 홍콩 | Green Label | U | 미작성 | 홍콩 그린라벨 — 화장품 품목 확인 |
| 419 | 이라크 | COSQC | U | 미작성 | 이라크 COSQC 적합성 — 화장품 포함 여부 확인 필요 |
| 424 | 이란 | ISIRI | U | 미작성 | 이란 ISIRI 강제인증 — 화장품 포함 여부 확인 필요 |
| 425 | 이란 | MOH | A | `IR_MOH` | 이란 MOH 화장품 등록 |
| 428 | 아랍에미레이트 | ECAS | B | `UAE_ECAS_GSO1943` | UAE ECAS — 화장품·퍼스널케어 적합성(GSO 1943) |
| 429 | 아랍에미레이트 | EQM | B | 미작성 | UAE EQM — 품질마크(화장품 적용 가능) |
| 434 | 우크라이나 | Ukr SEPRO | U | 미작성 | 우크라이나 제품인증 — 화장품 기술규정 적용 여부 확인 |
| 435 | 모로코 | DMP | A | `MA_DMP` | 모로코 DMP 화장품 사전등록 |
| 438 | 미얀마 | 미얀마FDA | A | `MM_FDA` | 미얀마 FDA 화장품 등록 |
| 440 | 이집트 | EDA | A | `EG_EDA` | 이집트 EDA 화장품 등록 |
| 442 | 뉴질랜드 | BIOGRO | B | 미작성 | 뉴질랜드 BioGro 유기농 — 화장품 기준 보유 |
| 444 | 뉴질랜드 | ECNZ | U | 미작성 | 뉴질랜드 환경라벨 — 화장품 품목 확인 |
| 448 | 캄보디아 | DDF | A | `KH_DDF` | 캄보디아 DDF 화장품 등록 |
| 452 | 우즈베키스탄 | GOST-UZ | U | 미작성 | 우즈베키스탄 적합성 인증 — 화장품 포함 여부 확인 |
| 453 | 카타르 | Qatar CoC | U | 미작성 | 카타르 CoC — 화장품 포함 여부 확인 필요 |
| 454 | 코트디부아르 | CI-VoC | U | 미작성 | 코트디부아르 VoC — 수입 전 적합성 검증, 화장품 포함 여부 확인 |
| 463 | 국제 | BeVeg Vegan Certified | M | 미작성 | BeVeg 비건 — 화장품 적용 |
| 469 | 국제 | Carbon neutral certification | M | 미작성 | 탄소중립 인증 |
| 475 | 국제 | Cradle to Cradle | M | 미작성 | Cradle to Cradle — 화장품 적용 사례 있음 |
| 478 | 국제 | EAC | A | `EAEU_TRCU009` | EAC — 유라시아 TR CU 009/2011 화장품 적합성 선언(EAEU 내 신청자 필요) |
| 479 | 국제 | Ecovadis | B | 미작성 | Ecovadis — 회사 ESG 평가(바이어 요구 시) |
| 486 | 국제 | EU Bio-based Products | M | 미작성 | EU 바이오기반 제품 — 클레임 |
| 487 | 국제 | FAIR TRADE | M | 미작성 | Fair Trade — 원료 공급망 |
| 501 | 국제 | HSNO APPROVAL | B | `NZ_HSNO_COSMETIC` | 뉴질랜드 HSNO — 화장품은 Cosmetic Products Group Standard 준수(등록 없음) |
| 512 | 국제 | International EPD | M | 미작성 | EPD — 환경성 선언 |
| 513 | 국제 | Intertek Green leaf mark | M | 미작성 | Intertek Green Leaf — 환경성 클레임 검증 |
| 515 | 국제 | ISCC | M | 미작성 | ISCC PLUS — 바이오기반 원료 공급망(원료사 중심) |
| 527 | 국제 | KOSHER | M | `KOSHER` | KOSHER — 코셔 화장품 가능(마케팅) |
| 534 | 국제 | NON GMO | M | 미작성 | Non-GMO Project — 퍼스널케어 인증 가능 |
| 537 | 국제 | OEKO-TEX® Standard 100 | B | 미작성 | OEKO-TEX 100 — 마스크팩 시트 원단(공급사) 적용 가능 |
| 539 | 국제 | OK Biodegradable Certification | B | 미작성 | OK Biodegradable — 포장재 |
| 540 | 국제 | OK compost | B | 미작성 | OK compost — 포장재 |
| 543 | 국제 | PFAS | U | 미작성 | PFAS — 무PFAS 검증 성격 확인 |
| 544 | 국제 | Product carbon footprint label | M | 미작성 | 탄소발자국 라벨 — 클레임 |
| 548 | 국제 | Rainforest Alliance | M | 미작성 | Rainforest Alliance — 원료 공급망 |
| 553 | 국제 | RSPO | B | `RSPO` | RSPO — 팜유 유래 성분(글리세린·지방산 에스터) 공급망 인증 |
| 556 | 국제 | SCS GLOBAL EPD | M | 미작성 | SCS EPD |
| 560 | 국제 | SMETA | B | 미작성 | SMETA — 회사 윤리감사 |
| 566 | 국제 | Toxproof | U | 미작성 | Toxproof — 화장품 품목 포함 여부 확인 |
| 572 | 국제 | Vegan Trademark | M | `VEGAN_SOCIETY` | Vegan Trademark(Vegan Society) — 화장품 적용 |
| 573 | 국제 | V-Label | M | `V_LABEL` | V-Label 비건 — 화장품 적용 |

미작성 B·M·U는 작업 범위(전략 5·국가 등록·지정 B 9·민간 12·국내) 밖이다. U(화장품 포함 여부 미확인) 15종은 확인 후 카드 또는 N으로 옮길 것. 583종에 없는 카드: 전략인증 4종(CPNP·SCPN·PPWR·HALAL), `AU_AICIS`, `LEAPING_BUNNY`, `VEGAN_KOREA`, 국내 카드 8종.

## 7. 미확인 항목(원문 대조 필요)

- **국가 등록 — 아직 2차·추정뿐인 곳**: 아르헨티나(조사 안 됨), 미얀마(fda.gov.mm 접속 실패 — JETRO·KCIA 2차), 모로코(ammps.ma 접속 불가 — 언론 2차), 이란(fda.gov.ir·ttac.ir 접속 불가 — 수입 금지 해제 현황 포함), 캄보디아 절차(Prakas 0187 원문·2025-11 신규 Prakas·수수료).
- **국가 등록 — 원문 반영 후 남은 세부(2026-11-07)**: 인도네시아 20/2026의 CFS·GMP 아포스티유·영사확인, PP 15/2026 요율, 'memutihkan' 표방 허용 여부 / 태국 2567 심사비 금액·수입 사업장 승인 서류 / 필리핀 AO 2024-0016 유예 해제 여부·LTO 유효기간 원문 / 말레이시아 라벨 Annex I part 7·스티커 / 베트남 신규 시행령 공포·아포스티유 CFS 수용, 제19조 베트남어 항목 원문 / 싱가포르 변형 정의·스티커 / 인도 계량법 세부·처리기간 / EAEU 결정 №74 내용·DoC·SGR 비용과 기간 / 브라질 통지 수수료·RDC 530 하이드로퀴논 / 멕시코 위생규칙(RCSPS)·2007 이후 Acuerdo 개정 / 안데스 결의 2108·2310(라벨·알레르겐)·페루 CFS·수수료 / UAE 공식 수수료·Montaji·새 Cabinet Decision·GSO 1943:2024 본문 / 이집트 공식 수수료·GOEIC / 호주 제품별 인벤토리 등재 여부 / 뉴질랜드 알파알부틴 제한 반영·라벨 언어.
- **통합표에 없는 성분 목록**: 영국 GB 부속서(XML 확보, 미적재), 아세안 ACD(HSA 게시본 확보, 미적재), 캐나다 Hotlist(HTML), GSO 1943(유료), 메르코수르·안데스, 인도 BIS, 이집트·모로코·이란, TR CU 009, 멕시코 고시, 뉴질랜드 그룹 표준, AICIS 인벤토리·SUSMP, Prop 65 목록, EU 에코라벨 배제 물질, 일본 의약부외품 첨가물, 한국 식약처 사용금지·제한(API 인증키 필요), 중국 2021 제74호·2026 제99호 금지표, 일본 化粧品基準 일본어명↔INCI 매핑.
- **EU**: Reg. 2023/1545 확대 알레르겐 전환일(2026-07-31 신규·2028-07-31 기존), free-from·저자극 표방 기준(EU 표시 기술문서), 나노 신고 세부, PPWR 전 항목(2025/40 원문 미대조), 에코라벨 기준 결정 번호·범위·수수료, 미세플라스틱 제한(2023/2055) 카드 필요 여부.
- **영국**: 확대 알레르겐 도입 여부, 라벨 세부, 수수료. **미국**: 21 CFR 700 금지 성분·색소 규정, 드럭 표방 경계, 주(州) 동물실험 판매 금지, Prop 65 경고 형식.
- **중국**: 효능 평가 방식(인체·소비자·실험실), 중문 라벨 세부, 연차보고, 특수 注册 심사 기간·수수료·注册证 유효기간, 무첨가 표방 제한. **일본**: MAH 요건·갱신, 라벨 항목, 화장품 효능 56항목, 의약부외품 승인 서류·기간·수수료·외국제조업자 인정 절차, 미백·주름 → 의약부외품 판단(○).
- **대만**: 현지 업체 요건, PIF 구성·서명자 자격, 동물실험 금지 시행일, 라벨 항목, 수수료·갱신 주기, 미백 성분의 특정용도 해당 여부.
- **할랄**: KMF·KHA 절차·서류·비용·기간·유효기간(사이트 접속 불가·JS), KMF-BS2016 원문, MS 2634 원문·에탄올 조항, Kepka 90/2023 원문(등록 유효기간·현행 수수료), LPPOM 수수료, GSO 2055-4 본문(유료), JAKIM 목록의 품목 범위, KTC 인정 여부.
- **민간 인증**: 비건 인증 비용(전 기관 비공개·견적), V-Label 화장품 동물실험 기준의 현행 위치(V02.03에서 조항 삭제), CFI 현행 요율표·중국 페이지, COSMOS 인증기관별 금액(Soil Association 404, ECOCERT·COSMECERT·IONC 견적)·ICEA 인정 상태, ECOCERT 자체 표준 V2 본문, NATRUE 심사비·기간, 한국 사무소 있는 USDA 인정 인증기관, ECARF·Dermatest 시험 기준·유효기간, Kosher, RSPO 모델·비용(이 4장은 이번 조사 범위 밖).
- **국내**: 동물실험 금지 조문(§15의2), 상세페이지 '21가지' 성분 목록, 기능성 심사·외국어 증명 처리기간, CGMP 영문 증명 절차, 협회 증명서 공증 필요 여부, 회사 상시근로자 수·연 생산액(안전성 평가 시행일 결정), 이노비즈 유효기간·자가진단 점수, 메인비즈 수수료, 벤처 평가 기간.
- **지원사업**: 전략·일반 인증별 세부 지원 비율과 한도, 비공고 인증(리핑버니·AICIS 등) 지원 여부, 국내 인증(VEGAN_KOREA) 지원 대상 여부.

## 8. 변경 이력

- 2026-11-07 오전: 카드 56장 작성, 엔진 규약(현지 책임자 키=관할 코드, 표방 ID=제품 데이터 토큰, 표방 효과는 조건부)에 맞춰 일괄 정리.
- 2026-11-07 12:00: 조사정리 §4-8(국내 제도·수출 서류, 법령·고시 원문 ◎) 반영 — `KR_RESPONSIBLE_SELLER`(서류 10종, 표방 규칙·`needs_evidence` 도입), `KR_FUNCTIONAL_REPORT`(보고 조건·이중 기능성·보고 0원·변경보고 없음, `claims_any`), `KR_CGMP`, `KR_VENTURE`, `KR_INNOBIZ`, `KR_MAINBIZ`(완전자본잠식·부채비율 결격 blocking) 보강, 새 카드 `KR_CFS_EXPORT`·`KR_SAFETY_ASSESSMENT` 추가, CFS를 요구하는 국가 카드 10장에 `cfs_kcia*` 힌트 연결.
- 2026-11-07 11:59: `EU_REACH_D4D5D6` 날짜를 EUR-Lex Reg. 2024/1328 원문과 대조해 수정(다른 작업자 수정분, 유지).
- 2026-11-07 12:03: `JP_QUASI_DRUG` 미백·주름 표방에 승인 전례 유효성분 `actives_any` 추가(다른 작업자 수정분, 유지 — 아데노신은 일본 주름 유효성분 아님).
- 2026-11-07 12:40: 다른 작업자가 `certcheck/classify.py`·`data.py`·`normalize.py`를 고침(금지 목록 예외 처리, 제한 목록 용도별 한도, 시험 충족을 서류 패턴으로 판정). 카드 규약 3절 `tests_required` 설명을 이 판에 맞춤.
- 2026-11-07 12:50: 국가별·민간 인증 조사 결과(아세안 2·유라시아·남미·중동·오세아니아·할랄·비건·유기농 보고서, 원문 인용 확인) 반영 — 카드 31장 갱신. 근거 수준 원문 19→44장·일부 원문 9→4장·2차+추정 30→10장, (추정) 769→354개, direct 근거 77→247개. 주요 판정 관련 변경: 아세안 8장 `labeling.allergens` 비움(ACD에 향료 알레르겐 표시 의무 없음), EAEU 2장·뉴질랜드·이집트·UAE는 알레르겐 값 채움, 아세안 미백·주름 표방 `drug_risk`, 브라질 미백·주름은 '별도 등록'이 아니라 2등급 통지+효능 자료(`needs_evidence`), 인도네시아 할랄 의무 2028-10-17 연장(PP 40/2026)으로 할랄 인증서를 필수 서류에서 뺌, `EAEU_SGR` 적용 대상을 부속서 12의 13종으로, 호주 미백·주름 표방 `drug_risk`(TGA). 판정 집계(P1~P4·COMPANY)는 수정 전과 같음 — 바뀐 근거는 모두 조건부 요인. 상세: `조사자료_20261107/국가별_인증카드_반영_20261107.md`.
