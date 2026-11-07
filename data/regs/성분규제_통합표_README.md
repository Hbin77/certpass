# 성분규제_통합표.csv — 생성 메모

> **2026-11-07 변경(운영진 데이터 검토 반영):** 중국(IECIC·화장품 안전기술규범 2015)과 대만(TFDA 목록) 원문 행은
> 운영진 검토에서 '사용 불가(저작권 확인 불가)'로 분류되어 이 표에서 **삭제**했다(14,358 → 2,642행, EU·JP만 남음).
> 중국·대만 금지·제한 판정은 식약처 화장품 사용제한 원료정보 API(`성분규제_식약처API.csv`, data.go.kr 15111772)로 대신한다.
> IECIC 등재 여부는 자동 판정하지 않고 '등재 확인 필요' 조건부 항목으로 안내한다. 아래 본문은 최초 생성 당시 기록이다.


- 생성일: 2026-11-07 (로컬 파일만 사용, 네트워크 조사 없음)
- 파일: `조사자료_20261107/성분규제_통합표.csv` — 14,358행, UTF-8(BOM 없음), 쉼표 구분, 셀 내 줄바꿈 없음(공백 1칸으로 정규화)
- 용도: "제품 전성분 → 국가별 금지/제한/허용 판정" 규칙 엔진의 데이터. 국가(EU/CN/JP/TW) × 목록 유형별 원문 규정을 한 스키마로 쌓은 **1차 산출물**이다. 정규화(INCI 사전 매핑, 함량 숫자화)는 아직 하지 않았다.
- 파싱 스크립트(세션 스크래치패드, 재실행용): `(작업용 임시 폴더)/parse_eu.py`, `parse_cn_spec.py`, `parse_iecic.py`, `parse_jp.py`, `parse_tw.py`, `merge_all.py`, `verify_lookup.py` (파이썬: 같은 폴더 `.venv-pdf/bin/python`, pdfplumber·openpyxl·xlrd 설치됨). 임시 폴더라 세션 종료 후 사라질 수 있음 → 필요하면 프로젝트로 복사.

## 1. 열 정의

| 열 | 내용 | 값 규약 |
|---|---|---|
| `jurisdiction` | EU / CN / JP / TW | |
| `list_type` | `banned`(금지) / `restricted`(제한) / `allowed_preservative`(허용 보존제) / `allowed_uv`(허용 자외선차단제) / `allowed_colorant`(허용 색소) / `inventory`(중국 已使用原料目录) | |
| `name` | 원문 명칭 | CN 규범: `중문명 \| 영문명`, CN 색소: `중문명 \| C.I. generic name \| CI번호`, TW 색소: `CI번호 \| 別名`. 구분자 ` \| ` |
| `inci` | INCI/표시명(있을 때) | EU: `Glossary명 \| Identified INGREDIENTS(쉼표열)`; CN 규범: INCI명칭 열; IECIC: INCI/영문명; TW: INCI名. JP는 모두 빈칸(일본어 성분명만 존재) |
| `cas` | CAS 번호, 복수는 `;` | 정규식으로 추출(`\d{2,7}-\d{2}-\d`). CN 금지표는 영문명 안의 `(CAS No. …)`에서 추출 |
| `max_conc` | 최대 함량 원문 | JP는 `g/100g` 단위 보완(`1.0g/100g`), `上限なし（○）`, `配合不可（空欄）`, `配合不可` 사용 |
| `product_scope` | 적용 제품군/부위 원문 | JP 3열표는 성분당 3행으로 분리(아래 참고) |
| `conditions` | 기타 제한·경고문 원문 요약 | EU: `Other: … \| Warning: … \| CMR: …`, CN: `… \| 标签: …`, TW: `… \| 注意事項: …`, JP: `注n: …` |
| `source_file` | 원본 파일(조사자료 폴더 기준 상대경로) | |
| `source_ref` | 부속서·표·항목 번호(+PDF 쪽) | 예 `Annex III ref 88`, `表3 化妆品限用组分 序号 21 (PDF p.110)`, `別表第3-2 No.1 p.7`, `化粧品成分使用限制表 編號 11` |
| `last_update` | 파일에 적힌 갱신일(YYYY-MM-DD) | EU는 행별 `Update Date`(파일 전체 Last update 2026-11-05), CN 규범 2015-12-23(공고일; 시행 2016-12-01), IECIC 2025-06-23(동봉 附件3 조정일로 추정), JP 2016-06-01(PDF 제목 H280601改正反映版), TW 보존제/UV/색소 2025-06-04(meta modifiedDate), TW 금지·제한은 **빈칸**(파일 내 날짜 없음) |

## 2. 소스별 행 수·파싱 방법·목록 의미

| 국가 | list_type | 원본 | 행 수 | 파싱 | 의미 |
|---|---|---|---|---|---|
| EU | banned | `규제원문_dl_cosing/annex_II.csv` | 1,758 | csv 모듈. 5줄 머리말 뒤 `Reference Number` 헤더 탐지, 셀 내 CRLF 공백화 | 네거티브(Annex II 금지) |
| EU | restricted | `annex_III.csv` | 381 | 동일 | 제한(Annex III, 조건부 허용) |
| EU | allowed_colorant | `annex_IV.csv` | 154 | 동일 + 열 어긋남 보정(아래) | 포지티브(색소는 목록 외 사용 불가) |
| EU | allowed_preservative | `annex_V.csv` | 58 | 동일 | 포지티브 |
| EU | allowed_uv | `annex_VI.csv` | 34 | 동일 | 포지티브 |
| CN | banned | `규제원문_dl_cn/spec2015.pdf` 表1(PDF p.12–99) + 表2 금지 동식물(p.100–105) | 1,290 + 98 = 1,388 | pdfplumber `extract_tables`(괘선표). 序号 빈 행은 앞 행에 병합. 머리말 기재 수(1,388)와 일치 | 네거티브 |
| CN | restricted | 表3(p.106–119) | 47 | 동일. 47항 일치 | 제한 |
| CN | allowed_preservative | 表4(p.120–126) | 51 | 동일. 51항 일치 | 포지티브 |
| CN | allowed_uv | 表5(p.127–129) | 27 | 동일. 27항 일치 | 포지티브 |
| CN | allowed_colorant | 表6(p.130–150) | 157 | 동일. 사용범위 1~4 열의 `＋`를 `product_scope` 문구로 변환. 157항 일치 | 포지티브 |
| CN | inventory | `규제원문_dl_cn/iecic1.xlsx` | 8,965 | openpyxl. 4행 설명문 뒤 `序号` 헤더. 序号 없는 별명 행 20개는 앞 행 `name`에 ` / `로 병합 | **등재 목록**(사용 이력 원료). 허가가 아니라 "신원료 등록 없이 쓸 수 있는 원료" 판정용. 备注에 `按照《化妆品安全技术规范》要求使用`(722건), `《化妆品安全技术规范》禁用原料`(52건) 표기 있음 → 규범 표와 교차 확인 필요 |
| JP | banned | `규제원문_dl_jp/std1.pdf` 別表第1(p.3) | 30 | pdfplumber 텍스트, 번호 목록 파싱 | 네거티브 |
| JP | restricted | 別表第2-1/2-2/2-3(p.4–5) | 28행(성분 17) | 단어 좌표(x,y) 기반 열 배정. 2-3은 3개 제품군 열 → 성분당 3행 | 제한 |
| JP | allowed_preservative | 別表第3-1/3-2(p.6–8) | 112행(성분 48) | 3-2는 성분당 3행 | 포지티브(보존제는 별표3 외 사용 불가) |
| JP | allowed_uv | 別表第4-1/4-2(p.9–11) | 87행(성분 33) | 4-2는 성분당 3행 | 포지티브 |
| TW | banned | `대만TFDA_규제목록/tw_203.out` | 659 | json | 네거티브(化粧品禁止使用成分表) |
| TW | restricted | `tw_199.out` | 186 | json | 제한(化粧品成分使用限制表) |
| TW | allowed_preservative | `d_173682.json` | 57 | json + `meta_173682.json` | 포지티브. 단 meta 주석: 목록 외 보존제라도 EU·미국·일본이 허용·한도 공고한 성분은 가장 엄격한 한도로 허용 |
| TW | allowed_uv | `d_173683.json` | 27 | json | 포지티브(동일한 EU/US/JP 준용 조항) |
| TW | allowed_colorant | `d_173686.json` | 152 | json. `使用範圍` 코드 1~4를 문구로 변환 | 포지티브(EU/US/JP 공고 색소 준용, 단 CI 11380 등 19항 제외) |

JP 3열표의 `product_scope` 값: ① `粘膜に使用されることがない化粧品のうち洗い流すもの`(비점막·세정) ② `…洗い流さないもの`(비점막·잔류) ③ `粘膜に使用されることがある化粧品`(점막 사용 가능). 원문 공란은 `配合不可（空欄）`, ○는 `上限なし（○）`로 적었다(注1).

## 3. 파싱 실패·누락·불확실한 부분 (반드시 읽을 것)

### EU (CosIng 내보내기)
- `search.json`은 "niacinamide" 검색 응답 1건(pageSize=1)만 담겨 있어 INCI·CAS·기능 사전으로 쓸 수 없었다. `annex_II.xls`는 CSV와 같은 내용이라 쓰지 않았다.
- Annex IV CSV는 CosIng 내보내기 자체가 열이 어긋나 있다(제품군 문구가 `Maximum concentration` 열에, 숫자 한도가 `Other` 열에). 숫자 없는 max_conc를 `product_scope`로, `%`/`ppm` 포함 Other를 `max_conc`로 옮기는 휴리스틱 적용(7건 영향). 원본 대조 권장.
- `inci`는 `Glossary명 | Identified INGREDIENTS`를 합친 것. Identified 목록은 **쉼표 구분이지만 INCI 자체에 쉼표가 있는 경우(`1,2-HEXANEDIOL`)가 있어 쉼표로 쪼개면 깨진다** → 토큰화 시 `쉼표 뒤가 영문자·공백 3자 이상`일 때만 분리 권장.
- Annex II 1,758행 중 1,439행이 INCI 없음(의약품·화학물질명만), 84행 CAS 없음. 금지물질 매칭은 CAS + 화학명 유사도 보조가 필요.
- `last_update`는 행별 `Update Date`(2010~2026). 파일 전체 Last update는 2026-11-05.

### CN 化妆品安全技术规范(2015판 PDF)
- **表7 准用染发剂(75항, PDF p.151–157)는 추출하지 않음**(요청 list_type에 없음). 필요 시 `parse_cn_spec.py`의 TABLES에 추가하면 같은 방식으로 뽑힌다.
- 2015판 원문이므로 2021·2024년 이후 증보(금지물질 추가·삭제, 표 개정)는 반영되지 않았다. 최신판 PDF를 받으면 쪽 범위(인쇄쪽+7=PDF쪽)만 다시 잡으면 된다.
- 한 序号 안에 (1)/(2) 하위항목이 있는 경우(表3 No.3 硼酸/四硼酸盐)는 **한 행에 합쳐짐**. (a)/(b) 표시가 없는 다중 라인 셀(表3 No.21 吡硫鎓锌: scope `去头屑淋洗类发用产品 驻留类发用产品`, max `1.5% 0.1%`)은 **순서로 대응**시켜 읽어야 한다.
- 각주 윗첨자 `(1)`,`(2)`를 이름에서 제거했고, 아래첨자 깨짐(`C -C ) 12 22`)은 `(C12-C22)`로 복원. 중문 사이 공백은 제거해 `(a)驻留类产品(b)淋洗类产品`처럼 붙어 있음. 줄바꿈 셀은 공백으로 이어져 `二苯酮-4 二苯酮-5`(表5 No.4) 같이 두 성분이 한 셀에 있을 수 있다.
- 表6 색소 `max_conc`는 `其他限制和要求`에 `最大浓度 x%`가 명시된 경우에만 채움(나머지 빈칸). 색소 불순물 한도는 `conditions`에 원문 그대로.
- 表1/表2에서 INCI 열은 없다(`inci` 빈칸 1,434행). CAS는 영문명 괄호에서 추출(435행은 CAS 없음, 주로 동식물·군(group) 항목).

### CN 已使用化妆品原料目录(IECIC) Ⅰ
- 파일에 판 날짜가 없다. 동봉 `f1.docx`(附件3 调整说明, 2025-06-23 조정)의 수정 내용이 xlsx에 반영돼 있어(序号 1371 刺芹, 1840 POWDER, 8970 苄氯酚 备注) **2025-06-23판으로 추정**해 `last_update`에 기록. 목록 Ⅱ(iecic2)는 자료에 없음.
- 序号는 최대 8970이지만 행은 8,965개(삭제 항목 공번). `**`가 붙은 비규범 명칭·중문만 있는 30행은 `inci` 빈칸.
- CAS·한도 정보 없음(원본에 없음). 등재 여부만 판정 가능.

### JP 化粧品基準
- **일본어 성분명만 있고 INCI·CAS가 없어, 영문 INCI로는 전혀 조회되지 않는다.** 규칙 엔진용으로는 일본어 성분명↔INCI 매핑표(예: 화장품 표시명칭·医薬部外品原料規格 대조표)가 별도로 필요하다. 검증 성분 22종 중 JP 표에 해당하는 것은 없음(글리세린은 総則 5 "DEG 0.1g/100g 이하" 조항이지만 별표가 아니라 행에 넣지 않았다).
- 괘선표에 행 구분선이 없어 pdfplumber `extract_tables`가 열만 묶고 행을 뭉개므로, 단어 좌표로 열을 배정하고 세로 간격(>10pt)으로 레코드를 끊는 방식으로 재구성했다. 디버그 출력(`parse_jp.py --debug`)으로 레코드 전수 육안 대조함(別表2-1 4, 2-2 15, 2-3 3, 3-1 16, 3-2 32, 4-1 6, 4-2 27 성분).
- 別表第1 No.2는 PDF 텍스트 박스가 잘려 `…以外の抗ヒスタミン`으로 끝남 → 공식 문구에 맞춰 `剤`를 보정(해당 행 `conditions`에 명시).
- 타르색소(別途 省令: 医薬品等に使用することができるタール色素を定める省令)는 자료에 없어 **JP allowed_colorant 행이 없다**. 赤色219号·黄色204号(모발·손톱 한정) 조항도 미수록.
- `std2.pdf/std2.txt`는 같은 고시의 전각숫자 판(개정 반영 전 판으로 보임)이라 쓰지 않음. `std1.pdf`(平成28년 6월 1일 개정 반영판) 사용. `qa_*`, `customs2020`, `pmda_c73`는 성분표가 아니어서 제외.

### TW TFDA
- `tw_203.out`(금지)·`tw_199.out`(제한)은 meta 파일이 없어 **갱신일 빈칸**. JSON 순서가 編號 순이 아니며(1,10,100,…), 編號 자체가 연속이 아니다.
- 금지표는 영문 성분명이 `name`에 있고 별도 INCI 열이 없어 `inci` 빈칸(659행). 영문명으로 매칭하면 된다.
- 색소표는 CAS 없음. `product_scope`는 코드 → `第n類: …` 문구.
- meta 주석(README 2절 참고): 보존제·UV·색소는 목록 외라도 EU/US/JP 허용 성분을 준용한다는 예외가 있어, "TW 목록에 없음 = 사용 불가"로 단정하면 틀린다.

### 공통
- 모든 `max_conc`/`product_scope`/`conditions`는 원문 문자열이다. 숫자 비교용 파싱(%, g/100g, ppm, (a)/(b) 분해)은 다음 단계.
- CJK 부분문자열 매칭은 오탐이 많다(예: `金盏花`(Calendula)로 검색하면 CN 금지 `侧金盏花`(Adonis)가 잡힘). 영문 INCI는 단어 경계, 중문은 완전일치 권장.
- pandas 로딩 예: `pd.read_csv(path, dtype=str, keep_default_na=False)`.

## 4. 검증 성분 22종 조회 결과 (영문 INCI 기준, `verify_lookup.py`)

exact = INCI/명칭 완전일치, related = 속(genus)·어근 수준 일치. "없음"은 해당 국가 표에 행이 없다는 뜻(= EU/CN규범/TW에서는 별도 제한 없음, CN IECIC에서는 **미등재 → 신원료 리스크**).

| 성분(추정 INCI) | EU | CN 规范 | CN IECIC | JP | TW | 메모 |
|---|---|---|---|---|---|---|
| 리모넨 Limonene | **restricted** Annex III 88: 잔류 0.001%(leave-on)/0.01%(rinse-off) 초과 시 전성분 표시 의무, 과산화물가 <20 mmol/L; related 129(terpenes) | 없음 | 등재 苧烯 序号8653 | 없음 | 없음 | 향료 알레르겐 표시 규칙 |
| 1,2-헥산다이올 1,2-Hexanediol | 없음 | 없음 | 등재 序号4 | 없음 | 없음 | |
| 에틸헥실글리세린 Ethylhexylglycerin | 없음 | 없음 | 등재 7706 | 없음 | 없음 | |
| 카프릴릴글라이콜 Caprylyl Glycol | 없음 | 없음 | 등재 7160 | 없음 | 없음 | |
| 펜타에리스리틸테트라-디-t-부틸하이드록시하이드로신나메이트 Pentaerythrityl Tetra-di-t-butyl Hydroxyhydrocinnamate | 없음 | 없음 | 등재 3247 | 없음 | 없음 | |
| PEG-20글리세릴트라이아이소스테아레이트 PEG-20 Glyceryl Triisostearate | 없음 | 없음 | 등재 577 | 없음 | 없음 | |
| 오렌지껍질오일 Citrus Aurantium Dulcis (Orange) Peel Oil | **restricted** Annex III 351(Citrus aurantium amara/dulcis peel oil: 'Citrus Aurantium Peel Oil'로 표시 의무, 알레르겐) | 없음 | 등재 6672 酸橙果皮油 | 없음 | 없음 | EU Annex II 358 푸로쿠마린(자연 함유 외 금지, 선케어·브론징 <1 mg/kg) 공통 적용 |
| 레몬껍질오일 Citrus Limon (Lemon) Peel Oil | **restricted** Annex III 353(표시 의무); **banned** Annex II 358 identified 목록에 Citrus limon 성분 포함(푸로쿠마린) | 없음 | 등재 4835 | 없음 | 없음 | |
| 자몽껍질오일 Citrus Paradisi (Grapefruit) Peel Oil / Citrus Grandis Peel Oil | Annex II 358 identified 목록(Citrus paradisi/grandis peel oil expressed) → 푸로쿠마린 한도 | 없음 | 등재 5161(PARADISI), 8179(GRANDIS) | 없음 | 없음 | |
| 라임오일 Citrus Aurantifolia (Lime) Oil | Annex II 358 identified 목록(Citrus aurantifolia peel oil expressed/distilled) | 없음 | 등재 4239 | 없음 | 없음 | 압착 라임오일은 광독성(푸로쿠마린) 주의 |
| 시벅톤오일 Hippophae Rhamnoides Oil | 없음 | 없음 | 등재 5870(OIL), 5865(FRUIT OIL) | 없음 | 없음 | |
| 카렌듈라꽃수 Calendula Officinalis Flower Water | 없음 | 없음 | **exact 없음** — FLOWER/FLOWER EXTRACT/FLOWER OIL/EXTRACT/SEED OIL만 등재(3499~3503) | 없음 | 없음 | CN 미등재 가능성 → 신원료 또는 FLOWER EXTRACT로 명칭 조정 검토 |
| 글리세린 Glycerin | 없음 | 없음 | 등재 2421 | 별표 없음(総則5: DEG ≤0.1g/100g, 행 미수록) | related: 금지 編號646 BSE 발생국 소·양 유래 원료(지방산·글리세린 등 처리 유도체는 제외) | |
| 합성왁스 Synthetic Wax | 없음 | 없음 | 등재 2771 | 없음 | 없음 | |
| 카프릴릭/카프릭트라이글리세라이드 Caprylic/Capric Triglyceride | 없음 | 없음 | 등재 7206 | 없음 | 없음 | |
| 세틸에틸헥사노에이트 Cetyl Ethylhexanoate | 없음 | 없음 | 등재 3561 | 없음 | 없음 | |
| PEG-10아이소스테아레이트 PEG-10 Isostearate | 없음 | 없음 | 등재 485 | 없음 | 없음 | |
| 소르비탄세스퀴올레이트 Sorbitan Sesquioleate | 없음 | 없음 | 등재 5915 | 없음 | 없음 | |
| 나이아신아마이드 Niacinamide | 없음 | 없음 | 등재 7359 | 없음 | 없음 | |
| 아데노신 Adenosine | 없음(Annex III 24 hit는 ZINC ADENOSINE TRIPHOSPHATE 오탐) | 없음 | 등재 6970 | 없음 | 없음 | |
| 알부틴 Arbutin | **restricted** Annex III 378: 7% 페이스크림, 하이드로퀴논 최소화(α-Arbutin은 377: 2% 페이스크림/0.5% 바디로션) | 없음(단 중국은 미백 기능성 = 特殊化妆品 등록 대상, 본 표 범위 밖) | 등재 7259(熊果苷), 1005(α-熊果苷) | 없음(일본은 医薬部外品 미백 유효성분, 본 표 범위 밖) | **restricted** 編號11: 7%, 불순물 Hydroquinone ≤20 ppm | |
| 레티놀 Retinol | **restricted** Annex III 376: 0.05% RE 바디로션 / 0.3% RE 기타(2025-11-01부터 적용) | 없음 | 등재 6162 | 없음 | 없음 | |

판정 요약: 22종 중 EU 제한 7종(리모넨·오렌지·레몬·알부틴·레티놀 + 자몽·라임의 푸로쿠마린 조항), TW 제한 1종(알부틴), CN 규범 해당 0종, CN IECIC 미등재 1종(카렌듈라꽃수), JP 별표 해당 0종(단 INCI 매핑 부재로 미검증).
