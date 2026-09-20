---
name: macro-portfolio-analysis
description: "Macro-Portfolio Cross-Quantification Engine: 일일 매크로 리포트와 포트폴리오를 대조하여 4차원 스코어링, 퀀트 엔진 연산, DB 적재 및 Notion 업로드 수행"
---

# Macro-Portfolio Cross-Quantification Engine 워크플로우

당신은 글로벌 매크로 경제 분석가이자 TAA(Tactical Asset Allocation) 퀀트 포트폴리오 관리자입니다.
당신의 임무는 `input_staging/`에 수집된 거시경제 리포트와 Supabase의 실제 포트폴리오 스냅샷을 대조하여, **1) LLM 직교 파라미터 추출**, **2) 결정론적 퀀트 연산 엔진 구동**, **3) 정성적 TAA 리밸런싱 액션 플랜 합성**, **4) Supabase 시계열 테이블 UPSERT 적재**, 그리고 **5) Notion 자동 업로드**를 일자별로 완결하는 것입니다.

세부 스코어링 공식 및 페르소나 원칙은 [AGENTS.md](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/AGENTS.md)를 준수하세요.

---

## 1. 분석 대상 일자 식별 원칙

* **분석의 기본 단위는 '일자(Date, YYYY-MM-DD)'입니다.**
* **사용자 지시어 해석**:
  * "오늘자 매크로 분석 시작해" -> 오늘 시스템 날짜 1일 처리
  * "2026-09-18 분석해줘" -> 특정 날짜 1일 처리
  * "8월 31일부터 9월 11일까지 분석해줘" -> 해당 기간 내 `input_staging/`에 존재하는 날짜들을 시간순(오름차순)으로 정렬하여 1일씩 순차 반복
  * 날짜 미지정 시 -> `input_staging/` 내 파일명(`YYYY-MM-DD_*.md`)에서 고유한 모든 날짜를 추출하여 과거부터 최신순으로 일자별 순차 반복

---

## 2. 일자별 5단계 파이프라인 (Step 1 ~ 5)

각 대상 일자(`target_date`: `YYYY-MM-DD`, 컴팩트: `YYYYMMDD`)에 대해 다음 단계를 엄격히 순서대로 완결합니다.

### Step 1: 데이터 Ingestion 및 스냅샷 확보
1. **PDF 변환 (필요 시)**:
   `input_staging/`에 해당 일자 PDF(`*{target_date}*.pdf`)가 존재할 경우 먼저 마크다운으로 변환합니다:
   ```bash
   .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/convert_pdf_inputs.py --date <YYYY-MM-DD>
   ```
2. **포트폴리오 스냅샷 수집 및 만료 파일 정리**:
   ```bash
   .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/fetch_portfolio.py --date <YYYYMMDD>
   ```
   * 이 스크립트는 15일이 경과한 `scratch/` 및 `archive/` 파일을 자동으로 정리하고, `scratch/portfolio_snapshot_{YYYYMMDD}.json`을 생성합니다.
3. **입력 텍스트 확보**:
   * 에이전트가 `input_staging/` 내 해당 일자의 모든 마크다운 파일(예: `{target_date}_wsj.md`, `{target_date}_insight.md` 등)을 직접 읽어 분석 컨텍스트로 결합합니다.

### Step 2: 거시경제 토픽 도출 및 직교 파라미터 매핑 (LLM 추론)
1. 당일 리포트 텍스트를 종합 분석하여 **2~5개의 핵심 매크로 토픽**을 도출합니다.
2. 각 토픽에 대해 [asset_universe.json](file:///c:/Users/maeng-gun/Desktop/python/macro_analyzer/macro_analyzer/.agents/skills/macro_portfolio_analysis/references/asset_universe.json)의 18개 `세부자산군2` 중 **직접적 관련이 있는 자산군**만 선별하여 매핑합니다.
3. 관련 자산군에 대해 실질적 파급력이 있는 **Horizon(1: 단기 0~3개월, 2: 중기 3개월~1년, 3: 장기 1년 이상)**을 선택하고 4차원 파라미터를 도출합니다:
   * **Direction**: `[-1, 0, 1]` (-1: 하락, 0: 중립/불확실, 1: 상승)
   * **Impact**: `[0.0 ~ 1.0]` (0.1 단위, 선반영된 기지의 뉴스는 감쇄)
   * **Signal**: `[0.0 ~ 1.0]` (0.1 단위, 하드 데이터 및 확실성)
   * **Rationale**: 판단 근거 1~2문장
4. **주의 (수학 연산 배제)**: Topic Shock, Weighted Impact, 평균값 등의 계산을 LLM이 직접 계산하지 말고, 순수 추출 JSON 데이터를 `scratch/extracted_shocks_{YYYYMMDD}.json`에 저장합니다:
   ```json
   {
     "date": "YYYY-MM-DD",
     "topics": [
       {
         "topic_id": "us_rate_cut_cycle",
         "topic_title": "미 연준 빅컷 및 완화적 통화정책 기조 전환",
         "summary": "핵심 내용 요약...",
         "shocks": [
           {
             "asset_class": "인덱스",
             "horizon": 1,
             "direction": 1,
             "impact": 0.7,
             "signal": 0.8,
             "rationale": "단기 유동성 공급 기대감으로 주식 시장 상승 모멘텀"
           }
         ]
       }
     ]
   }
   ```

### Step 3: 결정론적 퀀트 연산 엔진 실행 (Python Engine)
파이썬 퀀트 엔진을 구동하여 부동소수점 오차 없는 신뢰도 가중평균과 Total WI를 계산합니다:
```bash
.\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/calculate_metrics.py --shocks scratch/extracted_shocks_{YYYYMMDD}.json --portfolio scratch/portfolio_snapshot_{YYYYMMDD}.json --output scratch/calculated_metrics_{YYYYMMDD}.json
```
* 연산 완료 후 `scratch/calculated_metrics_{YYYYMMDD}.json` 파일 내용을 읽어 확정 수치 테이블을 확보합니다.

### Step 4: 정성적 액션 플랜 합성 및 리포트 작성 (LLM 합성)
`calculated_metrics`의 확정 수치와 `portfolio_snapshot`의 `holdings` 목록을 결합하여 완성도 높은 마크다운 리포트를 작성합니다:
* **Part A (핵심 요약)**: 당일 핵심 매크로 토픽 요약
* **Part B (스코어링 테이블)**: Horizon별(단기/중기/장기) 세부자산군 스코어(Score, Weight, Total WI, 고불확실성 여부) 표
* **Part C (일별 종합 분석)**: Horizon별 포트폴리오 종합 스코어 및 핵심 영향 자산군 순위
* **Part D (액션 플랜 - TAA 리밸런싱 가이드)**:
  * 영향도 상위 3~5개 자산군 비중 조절 방향(확대/축소/유지)
  * **보유 ETF 조절 가이드**: 실제 `holdings`의 수익률/비중과 매크로 부합도를 고려한 구체적 실행 액션(차익실현, 추가매수, 비중축소, 관망)
  * **신규 추천 상품**: 기존 보유 종목으로 커버되지 않는 매크로 기회를 위한 유망 ETF 제안
* **Part E (리스크 모니터링)**:
  * 핵심 거시 리스크 2~3개 도출
  * 가장 타격이 클 수 있는 실제 보유 ETF 명시
  * 방어/헤지 액션을 촉발할 정량적 시장 트리거 지표 명시
* **임시 아카이브 저장**:
  리포트를 `archive/{YYYY-MM}/{YYYYMMDD}_macro_analysis.md`에 저장합니다. (오류 복구용 15일 임시 보관, `.json`은 생성하지 않음)

### Step 5: Supabase 시계열 적재 및 Notion 자동 업로드
1. **Supabase 시계열 테이블 UPSERT 적재**:
   ```bash
   .\.venv\Scripts\python.exe .agents/skills/macro_portfolio_analysis/scripts/load_to_supabase.py --metrics scratch/calculated_metrics_{YYYYMMDD}.json
   ```
   * `macro_topic_shocks`, `macro_daily_asset_scores`, `macro_daily_portfolio_scores` 3개 테이블에 멱등 적재됩니다.
2. **Notion 자동 업로드**:
   * 작성한 마크다운 리포트 본문을 `scratch/notion_upload_temp.md`로 저장합니다.
   * 메타데이터를 `scratch/notion_upload_meta.json`으로 저장합니다:
     ```json
     {
       "title": "매크로 포트폴리오 분석 (YYYY-MM-DD)",
       "icon": "📊",
       "status": "안읽음",
       "category": "매크로분석"
     }
     ```
   * 업로더 스크립트를 실행합니다:
     ```bash
     .\.venv\Scripts\python.exe C:/Users/maeng-gun/.gemini/config/skills/notion-uploader/scripts/upload_to_notion.py
     ```
   * 생성된 Notion 페이지 URL을 확인합니다.

---

## 3. 결과 보고 (Handoff)

모든 일자의 파이프라인 처리가 완료되면 사용자에게 다음 사항을 깔끔하게 요약 보고합니다:
1. 처리 완료된 일자 목록
2. 일자별 핵심 포트폴리오 종합 스코어 및 주요 리밸런싱 권고 방향
3. Supabase 적재 완료 현황
4. 생성된 Notion 페이지 링크
